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

# Lowercase honorific / rank titles that prefix a proper name (`conte Ugolino`,
# `ser Brunetto`, `Traiano imperadore`). Like prepositions, they are allowed lowercase
# as long as the piece still carries at least one real name word.
_TITLE_WORDS = frozenset({
    "conte", "contessa", "ser", "messer", "frate", "fra", "re", "donno",
    "imperadore", "imperador", "imperadrice", "arcivescovo", "vescovo",
    "marchese", "duca", "papa", "san", "santa", "santo",
})

# Articles allowed lowercase only INSIDE a name (`Giacomo il Maggiore`), never leading:
# a leading article marks an epithet (`il Navarrese`, `la madre`), not a name.
_INFIX_ARTICLES = frozenset({"il", "lo", "la", "l'", "i", "gli", "le"})


def _is_name_word(w):
    """A single proper-name token, possibly an elided-particle form (`d'Aquino`,
    `l'Abbagliato`) where the segment after the apostrophe is capitalized."""
    if w[:1].isupper() and _CAP_NAME_RE.match(w):
        return True
    if "'" in w:
        head, _, tail = w.partition("'")
        if head.islower() and tail[:1].isupper() and _CAP_NAME_RE.match(tail):
            return True
    return False


def is_capitalized_name(piece):
    """A piece that looks like a proper-name sequence: every word is either a name word
    (capitalized, or an elided-particle form like `d'Aquino`) or an allowed lowercase
    connector — an Italian preposition (`della`, `da`, …), an honorific title
    (`conte`, `ser`, …), or an INFIX article (`Giacomo il Maggiore`) — and at least one
    real name word is present. A LEADING article (`il Navarrese`, `la madre`) is not a
    connector, so bare epithets/periphrases stay out and `Pier della Vigna`,
    `Guido da Montefeltro`, `Tommaso d'Aquino`, `conte Ugolino` qualify."""
    words = piece.split()
    if not words:
        return False
    has_name = False
    for i, w in enumerate(words):
        cf = w.casefold()
        if cf in _ITALIAN_PREPS or cf in _TITLE_WORDS:
            continue
        if i > 0 and cf in _INFIX_ARTICLES:
            continue
        if _is_name_word(w):
            has_name = True
            continue
        return False
    return has_name


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


# Demonstrative / deictic-pronoun heads. A label LED by one of these names a different figure in
# every scene (scene-local deixis), so it is not a stable individual node — it is typed `deictic`
# and dropped from the cast/cohort. A superset of the demonstrative subset of coreference.py's
# GOVERNORS; kept here so the typing step (04-tags/node_types.py) can classify deterministically.
DEICTIC_HEADS = frozenset({
    "quel", "quello", "quella", "quei", "quegli", "quelle",
    "questo", "questa", "questi", "queste",
    "costui", "costei", "costoro", "colui", "colei", "coloro",
    "chi", "cui", "ciò", "tale", "tali",
})


def is_deictic(label):
    """True if `label` is led by a demonstrative / deictic pronoun (DEICTIC_HEADS) — a scene-local
    reference ("quel cane", "colui che va giuso", "quel di Brescia") that names a different person
    per scene, so it is not a stable individual. Decided on the FIRST token alone, so real names
    (Guido, Pier della Vigna, San Pietro, la Pia) are never caught."""
    toks = norm_label(label).casefold().split()
    return bool(toks) and toks[0] in DEICTIC_HEADS


def mixed_bundle_pieces(label):
    """For a comma label that bundles named individual(s) with lowercase collective phrase(s)
    ("Dante, noble souls of Limbo"), return the lowercase (non-capitalized-name) pieces — the
    collective remainders that must be promoted to their own nodes so the whole label resolves as a
    SET (split_set) instead of a single `class` node that absorbs the individual. Returns [] when the
    label is not such a bundle: no comma, no capitalized-name piece (a pure epithet/appositive like
    "i pigri, lenti"), or every piece is already a capitalized name (a plain named set split_set
    handles)."""
    if "," not in label:
        return []
    pieces = [p for p in (norm_label(p) for p in label.split(",")) if p]
    if len(pieces) < 2:
        return []
    named = [p for p in pieces if is_capitalized_name(p)]
    rest = [p for p in pieces if not is_capitalized_name(p)]
    if not named or not rest:
        return []
    return rest


# First-person surface sets (case-folded), for speaker attribution in 06-speech.
# A strong first-person tag (`io`/`i'`) inside a quote's own region attributes the
# speaker; a weak one (`mi`/`me`) only does so as a fallback (signal: weak); plural
# first person never auto-attributes. number_scene already drops the supplied-subject
# `+`, so `[+io]`'s surface is `io` here.
FIRST_PERSON_STRONG = {"io", "i'", "ïo"}        # io, i', ïo
FIRST_PERSON_WEAK = {"mi", "m'", "me", "meco"}
FIRST_PERSON_PLURAL = {"noi", "ci", "ne"}
