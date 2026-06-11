"""
Person-reference markup for Dante's Divine Comedy (analysis step, pre-processing).

A deliberately LIGHT pass that makes every reference to a person in the grammar
EXPLICIT, on top of the source cantos, by adding inline marks to each source
line. Both layers run in a SINGLE PASS with one call per scene:

  Layer 1 — PRONOUNS  ([..] and [+..])
    - WRAP every personal / demonstrative / free-relative pronoun that stands for a
      person in [square brackets];
    - SUPPLY every omitted (pro-drop) subject as [+pronoun] just before its verb.
    e.g. "mi ritrovai per una selva oscura," -> "[+io] [mi] ritrovai per una selva oscura,".

  Layer 2 — NAMES     ({..})
    - WRAP every person-referring NOUN PHRASE (proper names and the common-noun
      epithets / periphrases that stand for a person) in {curly braces}.
    e.g. "{il Veltro} verrà", "rispuose '{l Poeta}'". Curly braces never collide
    with the [..] / [+..] pronoun marks already present, which are PRESERVED.

This is NOT resolution: it never names WHO a pronoun or epithet refers to — it only
marks references so a later step can resolve each. The model runs with CoT on
(include_thoughts=True; thinking is routed to a separate channel by Ollama).
Faithfulness is checked by round-trip — removing {..} braces, then [+..] insertions
and [] brackets must reproduce the source line verbatim.

Input:  canto source lines + scene ranges   (from the dante_corpus API; build the
        corpus first: make -C ../dante-corpus).
Output: 02-markup/<canticle>/NN.txt  — the marked lines, one per source line; the
        file is both the checkpoint and the committed output.
"""
import argparse
import re
import sys
import dante_corpus as dc
from dante_corpus import tokenize as _tokenize

from dante_analyze import MARKUP_DIR, load_scenes, call_llm, step_sep, MAX_LENGTH

OUT_DIR = MARKUP_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"


# ---------- inputs ----------

def read_lines(canticle, canto):
    """The readable full source lines of a canto, from the dante_corpus API."""
    return [line.text for line in dc.canto(canticle, canto).lines()]


def available_cantos(canticle):
    return list(dc.cantos(canticle))


# ---------- generic parsing & helpers ----------

LINE_RE = re.compile(r"^\s*(\d+)[:.\s]\s*(.*\S)\s*$")
INSERT_RE = re.compile(r"\[\+[^\]]*\]")   # a supplied (inserted) pronoun, e.g. [+io]
DOUBLED_SUPPLY_RE = re.compile(r"(\[\+[^\]]+\])\s+\1")  # adjacent duplicate [+x] [+x]
WS_RE = re.compile(r"\s+")


def parse_numbered(text):
    """{line_no: text} from the model's numbered reply (other lines ignored)."""
    out = {}
    for raw in text.splitlines():
        m = LINE_RE.match(raw)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def extraneous_lines(text):
    """Non-empty reply lines that are NOT a numbered output line — reasoning,
    headings, or a duplicated re-attempt (the model letting its chain-of-thought
    leak in). Code-fence lines (```) are allowed. A clean reply has none."""
    bad = []
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("```") and not LINE_RE.match(raw):
            bad.append(s)
    return bad


def norm(s):
    return WS_RE.sub(" ", s).strip()


def normalize_token_brackets(marked_line: str, src_line: str) -> str:
    """Expand [..] boundaries to token boundaries in src_line.

    If the model wrote [m]' but the tokenizer treats m' as one token, this
    expands the bracket to [m']. Only [..] brackets are adjusted; {..} name
    braces intentionally keep apostrophe-elided articles outside ('{l Poeta}).
    Token wider than bracket → expand. Token narrower → already fine (no-op).
    """
    src_chars = []   # list of [char, state], state: None or 'brk'
    insertions = {}  # index-in-src_chars -> ["+pronoun", ...]

    i = 0
    while i < len(marked_line):
        c = marked_line[i]
        if c == '[':
            j = marked_line.index(']', i)
            content = marked_line[i + 1:j]
            if content.startswith('+'):
                insertions.setdefault(len(src_chars), []).append(content)
            else:
                for ch in content:
                    src_chars.append([ch, 'brk'])
            i = j + 1
        elif c == '{':
            j = marked_line.index('}', i)
            for ch in marked_line[i + 1:j]:
                src_chars.append([ch, None])  # treated as plain for token scan
            i = j + 1
            src_chars.append(['\x00', 'nam_end'])  # sentinel to restore brace
        else:
            src_chars.append([c, None])
            i += 1

    # Reconstruct {..} spans from the original string for output purposes.
    # Simpler: re-parse to get {..} as opaque blocks in the output.
    # Strategy: only expand [..] across token boundaries; {..} blocks are
    # passed through unchanged by rebuilding from original parse.

    # Reset and redo: keep {..} contents as opaque 'nam' state (not scanned).
    src_chars = []
    insertions = {}
    name_spans = []   # (start_idx, end_idx) in src_chars for {..} contents

    i = 0
    while i < len(marked_line):
        c = marked_line[i]
        if c == '[':
            j = marked_line.index(']', i)
            content = marked_line[i + 1:j]
            if content.startswith('+'):
                insertions.setdefault(len(src_chars), []).append(content)
            else:
                for ch in content:
                    src_chars.append([ch, 'brk'])
            i = j + 1
        elif c == '{':
            j = marked_line.index('}', i)
            start = len(src_chars)
            for ch in marked_line[i + 1:j]:
                src_chars.append([ch, 'nam'])
            name_spans.append((start, len(src_chars)))
            i = j + 1
        else:
            src_chars.append([c, None])
            i += 1

    src_text = ''.join(c for c, _ in src_chars)
    tokens = _tokenize(src_text)

    pos = 0
    for token in tokens:
        tlen = len(token)
        states = {src_chars[pos + k][1] for k in range(tlen)}
        # Only expand [..]: if token spans brk and plain, pull plain chars into brk.
        # Skip if token touches 'nam' (name brace boundary — leave as-is).
        if 'brk' in states and None in states and 'nam' not in states:
            for k in range(tlen):
                if src_chars[pos + k][1] is None:
                    src_chars[pos + k][1] = 'brk'
        pos += tlen

    # Reconstruct output
    out = []

    def flush(state, chars):
        t = ''.join(chars)
        if state == 'brk':
            out.append(f'[{t}]')
        elif state == 'nam':
            out.append('{' + t + '}')
        else:
            out.append(t)

    cur_state = None
    cur_chars = []

    for idx, (ch, state) in enumerate(src_chars):
        if idx in insertions:
            if cur_chars:
                flush(cur_state, cur_chars)
                cur_chars = []
                cur_state = None
            for ins in insertions[idx]:
                out.append(f'[{ins}]')
        if state != cur_state:
            if cur_chars:
                flush(cur_state, cur_chars)
                cur_chars = []
            cur_state = state
        cur_chars.append(ch)

    end = len(src_chars)
    if end in insertions:
        if cur_chars:
            flush(cur_state, cur_chars)
            cur_chars = []
        for ins in insertions[end]:
            out.append(f'[{ins}]')
    elif cur_chars:
        flush(cur_state, cur_chars)

    return ''.join(out)


# ---------- unified layer (both pronoun and name marks in one pass) ----------

class UnifiedLayer:
    """Single pass: wrap person-pronouns in [..] / [+..] AND wrap person-referring
    noun phrases in {..} simultaneously. Round-trip basis is the raw source line:
    removing the {..} braces, then removing [+..] insertions and [] brackets, must
    reproduce the source verbatim."""
    name = "markup"

    RULES = """Rewrite each line adding two kinds of inline mark simultaneously:

────────────────────────────────────────────
LAYER 1 — PRONOUNS  (marks: [..] and [+..])
────────────────────────────────────────────

1. WRAP every existing pronoun that stands for a person in [square brackets]:
   - personal subject pronouns (io, i', tu, ei, elli, ella, noi, voi, …);
   - personal object / clitic pronouns (mi, m', ti, ci, vi when = "to us/you",
     si, s', lo, l', la, li, le, gli, ne when = "of them", lui, lei, me, te);
   - demonstrative or free-relative pronouns used for a PERSON (quei, questi,
     questa, costui, colui, chi, color).
   You MAY bracket an elided pronoun written with an apostrophe, wrapping just
   the pronoun and leaving the apostrophe in place. But do NOT bracket inside a
   word with no apostrophe: leave a verb with a pronoun fused solidly onto it whole.

2. SUPPLY every omitted (pro-drop) subject: insert the subject pronoun its
   conjugation implies, marked with a PLUS — [+io], [+tu], [+elli], [+ella],
   [+noi], [+voi] — in the subject position of its clause. In Italian, preverbal
   clitics (reflexive, object, and other clitic pronouns such as mi, ti, si, lo,
   la, gli, ci, vi, ne) form a cluster that attaches as a unit to the verb; the
   subject position is BEFORE that entire clitic cluster, never inside it.
   Insert NOTHING when the subject is already present in that clause as a noun, a
   pronoun, or a relative (che/chi/cui). The plus marks a word you ADDED; an
   existing word never gets it.
   "Its own clause" is strict and LOCAL: each finite verb needs its own subject.
   A subject standing in a DIFFERENT clause does NOT count — not in a relative
   clause, not in a coordinate clause, not in a previous line.

Do NOT bracket: possessives (mio, tuo, sua, nostra), the relative/conjunction
che or cui, a demonstrative ADJECTIVE directly modifying a following noun,
indefinite words (altrui, ciascun, qual, molti), or locative/partitive vi/ne.

────────────────────────────────────────────
LAYER 2 — PERSON NAMES  (marks: {..})
────────────────────────────────────────────

Wrap every PERSON-referring noun phrase in {curly braces}:
- proper names of a person: {Virgilio}, {Beatrice};
- a common-noun epithet, title, or periphrasis that STANDS FOR a person:
  - NARRATIVE context (subject, object, after a preposition): include the
    article — {il Veltro}, {la donna}, {lo savio};
  - VOCATIVE (direct address) or bare appositive with no article: mark only
    the bare noun/adjective phrase — {Poeta}, {famoso saggio};
  - an apostrophe-elided article in narrative context keeps the apostrophe
    OUTSIDE the span: '{l Poeta}', d'{i Toschi}.

Mark ONLY when the noun phrase refers to a PERSON or personified being.
Do NOT mark: pronouns (anything in [..] or [+..] stays as-is, never wrapped
in {..}); possessives or articles standing alone; place names, peoples,
abstractions, or animals; common nouns used metaphorically that do NOT
designate a person; a common noun not being used as a person-epithet.

Over-marking is acceptable for the name layer: marking a noun phrase you are
uncertain about is safer than leaving it unmarked.

────────────────────────────────────────────
CRITICAL: change NOTHING else.
────────────────────────────────────────────
Keep every original word, spelling, apostrophe, accent, and punctuation.
Apply both layers at the same time: remove your {..} braces, remove your
[+..] insertions, remove your [] brackets — the result must be the original
line verbatim."""

    @classmethod
    def build_scene_prompt(cls, canto, numbered, s, e):
        return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

Here is a passage of Canto {canto}, lines {s} to {e}, with line numbers:

```
{numbered.rstrip()}
```

{cls.RULES}

Output every line with its SAME number, one per line, and nothing else."""

    @classmethod
    def build_line_prompt(cls, canto, numbered_window, target):
        return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

Here are some lines of Canto {canto} for context (with line numbers):

```
{numbered_window.rstrip()}
```

{cls.RULES}

Rewrite ONLY line {target}. The other lines are context only and must NOT be in
your reply. Output exactly one line: the number {target} followed by the rewritten
line, and nothing else."""

    @classmethod
    def build_scene_retry_prompt(cls, problems, targets, lines):
        issues = "\n".join(f"- {p}" for p in problems)
        src = "".join(f"{i} {lines[i - 1]}\n" for i in targets)
        nums = ", ".join(str(i) for i in targets)
        return f"""Your previous reply has problems:
{issues}

Redo ONLY the line(s) below — reuse your earlier work for every other line and do
NOT repeat them here:

```
{src.rstrip()}
```

Output exactly the line(s) numbered {nums}, each number once, with nothing before,
between, or after them. Keep every original word, spelling, apostrophe, accent, and
punctuation; wrap pronouns in [..], insert supplied subjects as [+pronoun], and
wrap person noun phrases in {{..}}."""

    @staticmethod
    def stripped(reply):
        """Remove all marks to recover the original source line: first drop {..} braces
        (keeping contents), then remove [+..] insertions and [] brackets."""
        no_braces = reply.replace("{", "").replace("}", "")
        return norm(INSERT_RE.sub("", no_braces).replace("[", "").replace("]", ""))

    @classmethod
    def check_line(cls, reply, orig_line):
        """[] if the reply round-trips to the source; otherwise a one-item problem list."""
        if reply is None:
            return ["line is missing from the reply"]
        if cls.stripped(reply) != norm(orig_line):
            return [f"does not match the source after removing all marks "
                    f"(got: {cls.stripped(reply)!r})"]
        if reply.count("{") != reply.count("}"):
            return ["unbalanced curly braces"]
        if "{}" in reply.replace(" ", ""):
            return ["empty {} mark"]
        m = DOUBLED_SUPPLY_RE.search(reply)
        if m:
            return [f"adjacent duplicate supplied pronoun: {m.group(0)!r}"]
        return []


# ---------- round-trip check (display) ----------

def matches_source(marked_line, src_line):
    """True when removing all marks from the fully-marked line reproduces the source."""
    return UnifiedLayer.stripped(marked_line) == norm(src_line)


# ---------- LLM step ----------

LINE_CONTEXT = 4


def _normalize_replies(replies, lines):
    """Apply token-boundary normalization to each parsed reply in-place.
    Lines where normalization raises are removed so the retry loop re-requests them."""
    for i in list(replies):
        if 1 <= i <= len(lines):
            try:
                replies[i] = normalize_token_brackets(replies[i], lines[i - 1])
            except Exception:
                del replies[i]


def scene_problems(resp_text, s, e, lines, check):
    """Problems with a scene reply: leaked non-numbered text, and any line that
    does not round-trip to its source under `check`. Returns (problems, replies)."""
    problems = []
    if extraneous_lines(resp_text):
        problems.append("reply contains non-numbered text (reasoning, headings, or duplicates)")
    replies = parse_numbered(resp_text)
    _normalize_replies(replies, lines)
    for i in range(s, e + 1):
        for p in check(replies.get(i), lines[i - 1]):
            problems.append(f"line {i}: {p}")
    return problems, replies


def _resolve_scene(canto, lines, s, e, model, max_attempts, messages, label,
                   check, retry_prompt, max_length=MAX_LENGTH, include_thoughts=False):
    """Shared retry loop for the markup pass. `messages` is the initial conversation,
    ending with a user turn that asks for the numbered output; it is sent, then retried
    IN-CONVERSATION until every line round-trips: validated lines are ACCUMULATED across
    attempts (never discarded) and each follow-up turn re-requests ONLY the still-failing
    lines. Returns {line_no: line} for the lines that validated."""
    marked = {}
    for attempt in range(1, max_attempts + 1):
        resp = call_llm(messages, model, max_length=max_length, include_thoughts=include_thoughts)
        replies = parse_numbered(resp.text)
        _normalize_replies(replies, lines)
        for i in range(s, e + 1):
            if i not in marked and i in replies and not check(replies[i], lines[i - 1]):
                marked[i] = replies[i]
        pending = [i for i in range(s, e + 1) if i not in marked]
        leaked = extraneous_lines(resp.text)
        if not pending:
            if leaked:
                print(f"{label} scene {s}-{e}: attempt {attempt}/{max_attempts}: ignored "
                      f"{len(leaked)} non-numbered line(s) (leaked reasoning/headings); "
                      f"kept the validated numbered output", file=sys.stderr)
            break
        problems = []
        if leaked:
            problems.append("reply contains non-numbered text (reasoning, headings, or duplicates)")
        for i in pending:
            problems += [f"line {i}: {p}" for p in check(replies.get(i), lines[i - 1])]
        print(f"{label} scene {s}-{e}: attempt {attempt}/{max_attempts}: "
              f"{len(pending)} line(s) still need fixing: {pending}", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt < max_attempts:
            messages += [
                {"role": "assistant", "content": resp.text.strip()},
                {"role": "user", "content": retry_prompt(problems, pending, lines)},
            ]
    remaining = [i for i in range(s, e + 1) if i not in marked]
    if remaining:
        print(f"{label} scene {s}-{e}: NOT resolved — {len(remaining)} line(s) "
              f"still failing after {max_attempts} attempt(s): {remaining}", file=sys.stderr)
    else:
        print(f"{label} scene {s}-{e}: OK — all {e - s + 1} line(s) validated", file=sys.stderr)
    return marked


def mark_scene(canto, lines, s, e, model, max_attempts):
    """Mark one scene (single unified pass). Returns {line_no: marked_line} for lines
    that validated (still-failing lines are picked up by mark_one_line)."""
    numbered = "".join(f"{j} {lines[j - 1]}\n" for j in range(s, e + 1))
    messages = [{"role": "user", "content": UnifiedLayer.build_scene_prompt(canto, numbered, s, e)}]
    return _resolve_scene(canto, lines, s, e, model, max_attempts, messages,
                          "markup", UnifiedLayer.check_line, UnifiedLayer.build_scene_retry_prompt,
                          include_thoughts=True)


def mark_one_line(canto, lines, i, model, max_attempts):
    """Per-line redo: re-mark a single line with context, retrying in-conversation.
    Returns the validated marked line, or None if it never validates."""
    lo = max(1, i - LINE_CONTEXT)
    window = "".join(f"{j} {lines[j - 1]}\n" for j in range(lo, i + 1))
    messages = [{"role": "user", "content": UnifiedLayer.build_line_prompt(canto, window, i)}]
    for attempt in range(1, max_attempts + 1):
        resp = call_llm(messages, model, include_thoughts=True)
        problems, replies = scene_problems(resp.text, i, i, lines, UnifiedLayer.check_line)
        if not problems:
            print(f"line {i}: redo OK — resolved on attempt {attempt}/{max_attempts}",
                  file=sys.stderr)
            return replies[i]
        print(f"line {i}: redo {attempt}/{max_attempts}: {problems[0]}", file=sys.stderr)
        if attempt < max_attempts:
            messages += [
                {"role": "assistant", "content": resp.text.strip()},
                {"role": "user", "content": UnifiedLayer.build_scene_retry_prompt(problems, [i], lines)},
            ]
    print(f"line {i}: redo NOT resolved after {max_attempts} attempt(s); left unmarked",
          file=sys.stderr)
    return None


# ---------- driver ----------

def ck_path(canticle, canto):
    """Checkpoint and output path: 02-markup/<canticle>/NN.txt."""
    return OUT_DIR / canticle / f"{canto:02d}.txt"


def _save_lines(path, lines):
    """Write lines to checkpoint. Caller passes ck[:e] so file length == last scene end."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_run(canticle, model, only_canto=None):
    """Run the single-pass markup for each canto of `canticle`."""
    cantos = available_cantos(canticle)
    if not cantos:
        print(f"Error: no cantos for {canticle} in dante_corpus "
              f"(build it: make -C ../dante-corpus)", file=sys.stderr)
        sys.exit(1)

    if only_canto is not None:
        if only_canto not in cantos:
            print(f"Error: Canto {only_canto} not found for {canticle}", file=sys.stderr)
            sys.exit(1)
        targets = [only_canto]
    else:
        targets = cantos

    for canto in targets:
        checkpoint = ck_path(canticle, canto)
        lines = read_lines(canticle, canto)
        _, scenes_full = load_scenes(canticle, canto)
        scenes = [(s, e) for s, e, _ in scenes_full]
        last_end = max(e for _, e in scenes)

        if checkpoint.exists():
            n_saved = len(checkpoint.read_text(encoding="utf-8").splitlines())
            if n_saved >= last_end:
                print(f"Canto {canto}: already complete at {checkpoint}, skipping.")
                continue

        ck = list(lines)
        n_saved = 0
        if checkpoint.exists():
            saved = checkpoint.read_text(encoding="utf-8").splitlines()
            n_saved = len(saved)
            ck[:n_saved] = saved

        print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")

        failed = set()
        for s, e in scenes:
            if e <= n_saved:
                print(f"\n===== Canto {canto}, scene {s}-{e} [checkpoint: skipped] =====")
                continue
            print(f"\n===== Canto {canto}, scene {s}-{e} =====")
            step_sep("markup")
            ok = mark_scene(canto, lines, s, e, model, max_attempts=3)
            for i in ok:
                ck[i - 1] = ok[i]
            pending = [i for i in range(s, e + 1) if i not in ok]
            if pending:
                step_sep("per-line redo")
                print(f"scene {s}-{e}: {len(pending)} line(s) need a per-line redo: {pending}",
                      file=sys.stderr)
                for i in pending:
                    line = mark_one_line(canto, lines, i, model, max_attempts=3)
                    if line is None:
                        failed.add(i)
                    else:
                        ck[i - 1] = line
            _save_lines(checkpoint, ck[:e])
            print(f"saved {e} line(s) to {checkpoint}")

        if failed:
            print(f"WARNING: Canto {canto}: {len(failed)} line(s) left unmarked: {sorted(failed)}",
                  file=sys.stderr)

        print(f"\n===== Canto {canto} =====")
        print("\n".join(f"{' ' if matches_source(ln, lines[i - 1]) else '*'}{i} {ln}"
                        for i, ln in enumerate(ck, 1)))


def main():
    parser = argparse.ArgumentParser(
        description="Mark person references in Dante's Divina Commedia: pronouns "
                    "([..]/[+..]) and person names ({..}) in a single pass."
    )
    parser.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"LLM model (default: {DEFAULT_MODEL})")
    parser.add_argument("-c", "--canto", type=int,
                        help="Process only this canto.")
    args = parser.parse_args()

    for canticle in args.canticles:
        cmd_run(canticle, args.model, args.canto)


if __name__ == "__main__":
    main()
