"""Label normalization and classification for the registry pass.

These are the pure-code primitives the registry (`05-registry/`) builds on: an
identity-preserving grouping key (`norm_label`), a lossy collision-detection key
(`fold_key`), a set-label splitter (`split_set`), and the first-person surface sets
used for speaker attribution (`06-speech/`). No edit distance and no LLM here — these
only group what is exact-after-normalization; genuine near-dupes go to a human
inspection list, and the residual typing/grouping is a downstream LLM step.
"""
import re
import unicodedata

# Apostrophe variants the model and sources mix; all canonicalized to U+0027.
_APOSTROPHES = "’‘ʼ´`"
_APOS_RE = re.compile(f"[{_APOSTROPHES}]")
_WS_RE = re.compile(r"\s+")


def norm_label(label):
    """The identity-preserving grouping key: NFC, whitespace collapsed, apostrophes
    canonicalized to U+0027. This NEVER replaces committed spelling — it only removes
    cosmetic noise so two spellings that differ in nothing but form group together.
    The result is still a human-readable label (the registry's canonical heading is
    chosen from the raw labels of a group, not from this key)."""
    s = unicodedata.normalize("NFC", label)
    s = _APOS_RE.sub("'", s)
    return _WS_RE.sub(" ", s).strip()


# Leading articles stripped by fold_key. Elided forms (l'/'l) are listed so that
# `l'altra`, `la altra`, and `altra` all fold together (elision-insensitive).
_ELIDED_ARTICLE_RE = re.compile(r"^(?:l'|'l)\s*")
_ARTICLE_RE = re.compile(r"^(?:il|lo|la|i|gli|le|un|una)\s+")


def fold_key(label):
    """A lossy key for CANDIDATE collision detection only (never a stored label):
    case-folded, leading article stripped, elision-insensitive. Two labels with the
    same fold_key are flagged as a possible variant group for the registry to merge;
    the canonical spelling is always picked from the raw labels, not from this key.
    No edit distance — measurement shows exact-after-normalization covers the head."""
    s = norm_label(label).casefold()
    s = _ELIDED_ARTICLE_RE.sub("", s)
    s = _ARTICLE_RE.sub("", s)
    return s.strip()


_CAP_NAME_RE = re.compile(r"^[^\W\d_][\w']*(?:\s+[^\W\d_][\w']*)*$", re.UNICODE)

# Italian prepositions that appear lowercase inside proper names.
_ITALIAN_PREPS = frozenset({
    "di", "da", "della", "dello", "dei", "degli", "delle", "dell", "de'", "del",
})


def is_capitalized_name(piece):
    """A piece that looks like a proper-name sequence: every non-preposition word
    starts with an uppercase letter, and at least one such word is present.
    Italian prepositions (della, da, di, del, …) are allowed lowercase, so
    `Pier della Vigna` and `Guido da Montefeltro` qualify as names."""
    words = piece.split()
    if not words:
        return False
    non_preps = [w for w in words if w.casefold() not in _ITALIAN_PREPS]
    return bool(non_preps) and all(
        w[:1].isupper() and _CAP_NAME_RE.match(w) for w in non_preps
    )


def split_set(label, known_labels):
    """If `label` is a comma-joined SET of figures, return its members; else None.

    A label is a set iff it has a comma AND every comma-piece is itself either (a) a
    known standalone label (by fold_key) or (b) a capitalized name sequence. A label
    like `Cammilla, Eurialo, Turno, Niso` splits; a comma-bearing epithet like
    `quei che con lena affannata, uscito fuor del pelago a la riva` does NOT (its
    pieces are lowercase clauses), so it returns None and stays one label.
    """
    if "," not in label:
        return None
    known_folds = {fold_key(k) for k in known_labels}
    pieces = [norm_label(p) for p in label.split(",")]
    pieces = [p for p in pieces if p]
    if len(pieces) < 2:
        return None
    for piece in pieces:
        if fold_key(piece) in known_folds or is_capitalized_name(piece):
            continue
        return None
    return pieces


# First-person surface sets (case-folded), for speaker attribution in 06-speech.
# A strong first-person tag (`io`/`i'`) inside a quote's own region attributes the
# speaker; a weak one (`mi`/`me`) only does so as a fallback (signal: weak); plural
# first person never auto-attributes. number_scene already drops the supplied-subject
# `+`, so `[+io]`'s surface is `io` here.
FIRST_PERSON_STRONG = {"io", "i'", "ïo"}        # io, i', ïo
FIRST_PERSON_WEAK = {"mi", "m'", "me", "meco"}
FIRST_PERSON_PLURAL = {"noi", "ci", "ne"}
