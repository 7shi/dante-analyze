"""Deterministic text processing: numbered-tag splicing (`number_scene`), bullet
parsing, bracket normalization (`unbrace`), and Italian elision repair (`fix_elision`,
`ELIDE_RE`)."""
import re

MARK_RE = re.compile(r"\[[^\]]*\]|\{[^}]*\}")  # one [..]/[+..] or {..} mark


def number_scene(lines, s, e):
    """Splice a scene-local index into every mark of lines s..e.

    Returns (tagged_text, k, meta): `tagged_text` is the numbered lines joined with
    their line numbers ("12 …"), `k` the count of tags, and `meta` maps each tag
    number to `(kind, surface)` — kind is "pron" for a `[..]`/`[+..]` pronoun or
    "name" for a `{..]` person name, surface is the marked word(s) (the leading
    `+` of a supplied subject dropped). The n-th mark in appearance order becomes
    `[n:…]` / `{n:…}` (number after the opening delimiter, original delimiter kept);
    the tags resolution then refers to a mark as the bare `[n]`. `meta` lets the
    check catch a pronoun tag whose resolution merely echoes the pronoun, and carries
    each tag's SURFACE form so downstream code can pair surface with identity without
    asking the LLM for it."""
    counter = 0
    meta = {}
    out = []

    def repl(m):
        nonlocal counter
        counter += 1
        tok = m.group(0)
        surface = tok[1:-1].lstrip("+")
        meta[counter] = ("name" if tok[0] == "{" else "pron", surface)
        return f"{tok[0]}{counter}:{tok[1:-1]}{tok[-1]}"

    for ln in range(s, e + 1):
        out.append(f"{ln} {MARK_RE.sub(repl, lines[ln - 1])}")
    return "\n".join(out), counter, meta


def _append_collapsed(src, text):
    """Append `text` to the char list `src`, collapsing whitespace the way the markup
    round-trip's `norm` does (no leading space, runs of whitespace -> one space), so the
    reconstructed string stays char-aligned with the un-marked source line."""
    for ch in text:
        if ch.isspace():
            if src and src[-1] != " ":
                src.append(" ")
        else:
            src.append(ch)


def tag_positions(lines, s, e):
    """{tag_no: (line_no, col)} for every mark in lines s..e — the source-line position
    of each numbered tag, sharing `number_scene`'s appearance-order numbering (tag n here
    is tag [n] there). `col` is the 0-based column of the surface's first character IN THE
    SOURCE line (the un-marked text), computed by reconstructing the source as the scan
    proceeds and reading off its length at each mark; whitespace is collapsed exactly as
    the markup round-trip's `norm`, so the reconstruction is char-aligned
    with `canto.line(n).text`. A supplied subject (`[+io]`, not in the source) contributes
    no source characters, so it takes the column of the word it precedes — which is what
    its containment test against a quote span needs. Separate from `number_scene` so its
    `meta` shape (indexed by tags.py's check) is never disturbed."""
    counter = 0
    pos = {}
    for ln in range(s, e + 1):
        line = lines[ln - 1]
        src = []
        i = 0
        for m in MARK_RE.finditer(line):
            _append_collapsed(src, line[i:m.start()])
            counter += 1
            pos[counter] = (ln, len(src))
            tok = m.group(0)
            surface = tok[1:-1].lstrip("+")
            inserted = tok[0] == "[" and tok[1:2] == "+"
            if not inserted:  # a supplied subject is absent from the source
                _append_collapsed(src, surface)
            i = m.end()
        _append_collapsed(src, line[i:])
    return pos


def strip_to_source(line):
    """Reconstruct the un-marked source text of one markup line: unwrap every [..]/{..}
    mark to its surface (leading `+` of a supplied subject dropped, and a supplied subject
    `[+..]` contributes nothing — it is absent from the source), collapsing whitespace the
    way the markup round-trip's `norm` does. The result is char-aligned with
    `canto.line(n).text`, so the speech pass can assert the column math round-trips. Shares
    `_append_collapsed` with `tag_positions` so the markup->source collapse is single-sourced."""
    src = []
    i = 0
    for m in MARK_RE.finditer(line):
        _append_collapsed(src, line[i:m.start()])
        tok = m.group(0)
        surface = tok[1:-1].lstrip("+")
        inserted = tok[0] == "[" and tok[1:2] == "+"
        if not inserted:  # a supplied subject is absent from the source
            _append_collapsed(src, surface)
        i = m.end()
    _append_collapsed(src, line[i:])
    return "".join(src)


BULLET_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


def parse_bullets(text):
    """Lines that look like a bullet ('- …'), stripped of the marker."""
    return [m.group(1) for raw in text.splitlines() if (m := BULLET_RE.match(raw))]


def unbrace(text):
    """Mechanically normalize a model reply's bracket cosmetics: make `[ ]` the ONLY bracket
    delimiter (a name tag cited with its source brace, `{4}`, becomes `[4]`) and drop backtick
    wrapping (`` `[1]` `` -> `[1]`). Applied at the reply boundary so the NORMALIZED text is what
    goes into the conversation history — otherwise the model sees its own `{4}` / `` `[1]` `` in a
    prior turn and keeps echoing it, dragging it through later turns. Only the
    model's replies are rewritten; the source markup in the prompt keeps `[..]`/`{..}`, which is
    how pronoun vs. name marks are distinguished there."""
    return text.replace("{", "[").replace("}", "]").replace("`", "")


# Elision auto-fix. The model sometimes writes a label with an elidable determiner left
# un-elided where Italian REQUIRES elision before a vowel (`l'altra` as `la altra`). This is a
# mechanical quirk with one canonical form, so tags.py applies the repair IN CODE at generation
# time — no prompt clause asks the model to fix orthography (the old 05-tags
# clause over-corrected). These determiners all elide the same way — drop
# the final vowel and join the next word with an apostrophe (`lo`->`l'`, `una`->`un'`,
# `nello`->`nell'`, `quella`->`quell'`). The apostrophe written is U+0027 (ASCII `'`).
ELIDE_WORDS = (
    "lo", "la", "una",
    "dello", "della", "nello", "nella", "allo", "alla",
    "dallo", "dalla", "sullo", "sulla",
    "quello", "quella", "questo", "questa",
)
_VOWEL = "aeiouàèéìíòóùúAEIOUÀÈÉÌÍÒÓÙÚ"
ELIDE_RE = re.compile(
    r"\b(" + "|".join(ELIDE_WORDS) + r")\s+([" + _VOWEL + r"]\w*)", re.IGNORECASE
)


def fix_elision(label):
    """Repair the tags pass's de-elision over-correction: an elidable determiner left
    un-elided before a vowel (`la altra`, `nello uccello`) is contracted to the form Italian
    requires (`l'altra`, `nell'uccello`), the apostrophe being U+0027. Drops the determiner's
    final vowel and joins the next word; case is preserved (`La altra` -> `L'altra`). Other
    text is untouched, so an already-correct or unrelated label passes through unchanged."""
    return ELIDE_RE.sub(lambda m: f"{m.group(1)[:-1]}'{m.group(2)}", label)
