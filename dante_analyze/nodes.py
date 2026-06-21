"""Code-merged node set over the committed 04-tags labels — the fold shared by the registry build
(`05-registry/registry.py`, which renders + types-checks it) and the typing step
(`04-tags/node_types.py`, which classifies its canonicals). Promoted here because it is reused across
those two passes; both must fold identically, so the fold lives in one place.

`Nodes` gathers every per-scene `04-tags` label, merges by `fold_key` (canonical = most frequent
spelling, decided GLOBALLY so a cross-canticle figure shares one label), and exposes the per-canticle
spellings/surfaces and set membership. `apply_coref` selects whether the gather reads the
coreference-overlay-applied labels (the registry render, default) or the raw committed labels (the
typing step, which must be overlay-free so its cache is a superset of every label ever seen)."""
from collections import Counter, defaultdict

from ._paths import TAGS_DIR
from .corpus import read_markup
from .checkpoint import load_tags
from .marks import number_scene
from .labels import norm_label, fold_key, split_set, mixed_bundle_pieces

UNKNOWN = "(unknown)"

# Closed typing vocabulary shared by the typing step (which assigns it) and the registry structural
# check (which validates every node carries one of these). `deictic` is assigned deterministically
# (is_deictic) for scene-local demonstrative/periphrastic labels and dropped from cast/cohort.
TYPES = ("individual", "generic", "class", "hypothetical-simile", "non-person", "deictic")


def committed_cantos(canticle):
    """Cantos with a committed 04-tags file, in order; the file is the checkpoint."""
    d = TAGS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


class Nodes:
    """The code-merged node set over all three canticles. `key` is fold_key(canonical).

    - labels[key]: global Counter of norm_label spellings -> canonical (most frequent, tie by spelling)
    - labels_canticle[key][canticle]: Counter of spellings that occurred in that canticle
    - surfaces[key][canticle]: Counter of marked surface forms -> counts (per canticle)
    `(unknown)` is excluded from nodes (exempt from the assignment check, as in measure.py).

    `apply_coref` is threaded to `load_tags`: True (default) reads overlay-applied labels — the
    registry render reflects the coreference merges; False reads the raw committed labels — the
    typing step must be overlay-free so types.txt stays an append-only superset.
    """

    def __init__(self, canticles, apply_coref=True):
        self.apply_coref = apply_coref
        self.labels = defaultdict(Counter)
        self.labels_canticle = defaultdict(lambda: defaultdict(Counter))
        self.surfaces = defaultdict(lambda: defaultdict(Counter))
        self.distinct_canticle = defaultdict(set)   # canticle -> {norm_label} (for the check)
        for canticle in canticles:
            self._gather(canticle)

    def _add_label(self, canticle, nl, surface):
        key = fold_key(nl)
        self.labels[key][nl] += 1
        self.labels_canticle[key][canticle][nl] += 1
        self.distinct_canticle[canticle].add(nl)
        self.surfaces[key][canticle][surface] += 1

    def _gather(self, canticle):
        for canto in committed_cantos(canticle):
            markup = read_markup(canticle, canto)
            tags = load_tags(canticle, canto, apply_coref=self.apply_coref)
            for (s, e), res in tags.items():
                _text, _k, meta = number_scene(markup, s, e)
                for tag_no, raw in res.items():
                    nl = norm_label(raw)
                    if nl == UNKNOWN:
                        continue
                    _kind, surface = meta[tag_no]
                    self._add_label(canticle, nl, surface)
                    # Mixed individual+collective bundle ("Dante, noble souls of Limbo"): promote
                    # each lowercase collective piece to its own node so the whole label resolves as
                    # a SET (split_set) — the individual is no longer absorbed into a `class` node.
                    for piece in mixed_bundle_pieces(nl):
                        self._add_label(canticle, piece, surface)

    def canonical(self, key):
        """Most frequent global spelling of the node (tie broken by spelling)."""
        return max(self.labels[key].items(), key=lambda kv: (kv[1], kv[0]))[0]

    @property
    def canonicals(self):
        return {self.canonical(k) for k in self.labels}

    def members(self, key):
        """Set members if the node's canonical label is a comma-set, else None."""
        return split_set(self.canonical(key), self.canonicals)

    def keys_in(self, canticle):
        """Node keys occurring in `canticle`, sorted by descending in-canticle count then label."""
        keys = [k for k in self.labels if canticle in self.labels_canticle[k]]
        return sorted(keys, key=lambda k: (-sum(self.surfaces[k][canticle].values()),
                                           self.canonical(k)))
