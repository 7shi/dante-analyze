#!/usr/bin/env python
"""
Measurement-first probe of the committed 04-tags outputs for the registry build.

Pure code, no LLM, writes nothing — a stdout report that sizes the registry problem BEFORE any
registry prompt is frozen. It answers: how many distinct labels, how head-concentrated, how many
post-normalization variant groups remain, how many comma-labels are real sets vs. epithets, how
much `(unknown)`/typo noise, and — column-aware via marks.tag_positions + quotespans — how well
quote spans resolve to a first-person speaker. The decision gates at the end say whether the LLM
residual is one batched grouping+typing step or needs rethinking.

Runs on whatever 04-tags cantos are committed (glob, not available_cantos which tracks markup), so
it is meaningful on a partial run and re-runnable on the full one. Reads only committed artifacts:
04-tags (labels), 02-markup + 03-reading (noise check), and dante_corpus (source text, quotes).
"""
import argparse
import re
import sys
from collections import Counter, defaultdict

from dante_corpus import api

from dante_analyze import (
    TAGS_DIR,
    read_markup, load_tags, load_readings, load_scenes,
    number_scene, tag_positions,
    norm_label, fold_key, split_set,
    walk_spans, own_region,
    FIRST_PERSON_STRONG, FIRST_PERSON_WEAK, FIRST_PERSON_PLURAL,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
UNKNOWN = "(unknown)"
TOP_N = 15
LIST_CAP = 40  # cap on human-inspection lists so the report stays readable

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def tokens_of(text):
    """Case-folded alphabetic tokens of a string (≥2 chars), for the noise check."""
    return {t for t in (w.casefold() for w in _WORD_RE.findall(text)) if len(t) >= 2}


def committed_cantos(canticle):
    """Cantos with a committed 04-tags file, in order; the file is the checkpoint."""
    d = TAGS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


class CanticleData:
    """Everything the report needs for one canticle, gathered once."""

    def __init__(self, canticle):
        self.canticle = canticle
        self.records = []            # (canto, s, e, tag_no, raw_label)
        self.label_scenes = defaultdict(set)   # norm_label -> {(canto, s, e)}
        self.label_count = Counter()           # norm_label -> occurrences
        self.unknowns = []           # (canto, s, e, tag_no)
        self.noise = []              # (canto, s, e, raw_label) singleton, tokens absent
        self.spans_total = 0
        self.span_buckets = Counter()
        self.cross_scene_spans = []  # (canto, quote_id)
        self._gather()

    def _gather(self):
        for canto in committed_cantos(self.canticle):
            markup = read_markup(self.canticle, canto)
            tags = load_tags(self.canticle, canto)
            readings = load_readings(self.canticle, canto)
            cobj = api.canto(self.canticle, canto)

            # Per-canto referent table: (line, col, norm_label, surface_fold) across all scenes.
            referents = []
            scene_of_line = {}  # line_no -> (s, e), to detect scene-crossing spans
            for (s, e), res in tags.items():
                _text, _k, meta = number_scene(markup, s, e)
                pos = tag_positions(markup, s, e)
                for ln in range(s, e + 1):
                    scene_of_line[ln] = (s, e)
                # noise check material for this scene
                src_tokens = set()
                for ln in range(s, e + 1):
                    src_tokens |= tokens_of(cobj.line(ln).text)
                read_tokens = tokens_of(readings.get((s, e), ""))
                scene_tokens = src_tokens | read_tokens

                for tag_no, raw in res.items():
                    nl = norm_label(raw)
                    self.records.append((canto, s, e, tag_no, raw))
                    self.label_count[nl] += 1
                    self.label_scenes[nl].add((canto, s, e))
                    if nl == UNKNOWN:
                        self.unknowns.append((canto, s, e, tag_no))
                    line, col = pos[tag_no]
                    _kind, surface = meta[tag_no]
                    referents.append((line, col, nl, surface.casefold()))

            # quote coverage (column-aware)
            for span, _depth in walk_spans(cobj.quotes()):
                self.spans_total += 1
                if scene_of_line.get(span.start_line) != scene_of_line.get(span.end_line):
                    self.cross_scene_spans.append((canto, span.quote_id))
                strong, weak, plural = set(), set(), set()
                for line, col, nl, surf in referents:
                    if not own_region(span, line, col):
                        continue
                    if surf in FIRST_PERSON_STRONG:
                        strong.add(nl)
                    elif surf in FIRST_PERSON_WEAK:
                        weak.add(nl)
                    elif surf in FIRST_PERSON_PLURAL:
                        plural.add(nl)
                if len(strong) == 1:
                    self.span_buckets["strong-unique"] += 1
                elif len(strong) > 1:
                    self.span_buckets["multi-strong"] += 1
                elif weak:
                    self.span_buckets["weak-only"] += 1
                elif plural:
                    self.span_buckets["plural-only"] += 1
                else:
                    self.span_buckets["none"] += 1

        self._finalize_noise()

    def _finalize_noise(self):
        # rebuild scene token sets lazily; recompute for singleton labels only
        singletons = {nl for nl, c in self.label_count.items() if c == 1 and nl != UNKNOWN}
        if not singletons:
            return
        # map norm_label -> its single (canto, s, e)
        for (canto, s, e, tag_no, raw) in self.records:
            nl = norm_label(raw)
            if nl not in singletons:
                continue
            cobj = api.canto(self.canticle, canto)
            src_tokens = set()
            for ln in range(s, e + 1):
                src_tokens |= tokens_of(cobj.line(ln).text)
            readings = load_readings(self.canticle, canto)
            scene_tokens = src_tokens | tokens_of(readings.get((s, e), ""))
            label_tokens = tokens_of(raw)
            if label_tokens and not (label_tokens & scene_tokens):
                self.noise.append((canto, s, e, raw))

    @property
    def distinct(self):
        return set(self.label_count)


# ---------- report sections ----------

def section_label_stats(data):
    print(f"  tag lines (resolution rows): {sum(data.label_count.values())}")
    print(f"  distinct labels (normalized): {len(data.distinct)}")
    singletons = sum(1 for c in data.label_count.values() if c == 1)
    print(f"  singletons (appear once): {singletons}")
    print(f"  top {TOP_N} labels:")
    for label, n in data.label_count.most_common(TOP_N):
        scenes = len(data.label_scenes[label])
        cantos = len({c for (c, _s, _e) in data.label_scenes[label]})
        print(f"    {n:5d}  {label}   (scenes {scenes}, cantos {cantos})")


def fold_groups(distinct):
    """fold_key -> set of distinct norm_labels (a variant-candidate group if >1)."""
    groups = defaultdict(set)
    for nl in distinct:
        groups[fold_key(nl)].add(nl)
    return {k: v for k, v in groups.items() if len(v) > 1}


def section_variants(data):
    groups = fold_groups(data.distinct)
    print(f"  fold_key collision groups (>1 spelling): {len(groups)}")
    for key, members in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:LIST_CAP]:
        shown = sorted(members, key=lambda m: -data.label_count[m])
        print(f"    [{key}] " + " | ".join(f"{m} ({data.label_count[m]})" for m in shown))
    if len(groups) > LIST_CAP:
        print(f"    … {len(groups) - LIST_CAP} more groups")


def piece_qualifies(piece, known_folds):
    return fold_key(piece) in known_folds or _is_cap_name(piece)


def _is_cap_name(piece):
    words = piece.split()
    return bool(words) and all(w[:1].isupper() for w in words)


def section_sets(data):
    known = data.distinct
    known_folds = {fold_key(k) for k in known}
    confirmed, epithet, undecidable = [], [], []
    for nl in data.distinct:
        if "," not in nl:
            continue
        members = split_set(nl, known)
        if members:
            confirmed.append((nl, members))
            continue
        pieces = [p.strip() for p in nl.split(",") if p.strip()]
        quals = [piece_qualifies(p, known_folds) for p in pieces]
        if any(quals):
            undecidable.append(nl)
        else:
            epithet.append(nl)
    print(f"  comma-labels: confirmed sets {len(confirmed)}, "
          f"comma-epithets {len(epithet)}, undecidable(mixed) {len(undecidable)}")
    for nl, members in confirmed[:LIST_CAP]:
        print(f"    SET   {nl}  ->  {' | '.join(members)}")
    for nl in undecidable[:LIST_CAP]:
        print(f"    MIXED {nl}")
    return confirmed, epithet, undecidable


def section_noise(data):
    print(f"  {UNKNOWN} occurrences: {len(data.unknowns)}")
    for (canto, s, e, tag_no) in data.unknowns[:LIST_CAP]:
        print(f"    {data.canticle} {canto:02d} scene {s}-{e} tag [{tag_no}]")
    print(f"  singleton labels with NO token in source or reading "
          f"(weak typo signal — readings are English, so Italian names over-flag): "
          f"{len(data.noise)}")
    for (canto, s, e, raw) in data.noise[:LIST_CAP]:
        print(f"    {data.canticle} {canto:02d} scene {s}-{e}: {raw!r}")


def section_quotes(data):
    print(f"  quote spans: {data.spans_total}")
    for bucket in ("strong-unique", "multi-strong", "weak-only", "plural-only", "none"):
        print(f"    {bucket:14s}: {data.span_buckets.get(bucket, 0)}")
    print(f"  scene-boundary-crossing spans: {len(data.cross_scene_spans)}")
    for (canto, qid) in data.cross_scene_spans[:LIST_CAP]:
        print(f"    {data.canticle} {canto:02d} quote {qid}")


def report(data):
    print(f"\n{'=' * 70}\n# {data.canticle}\n{'=' * 70}")
    print("\n## 1. Label stats")
    section_label_stats(data)
    print("\n## 2. Variant candidates (fold_key collisions; human inspection)")
    section_variants(data)
    print("\n## 3. Set-valued labels")
    section_sets(data)
    print("\n## 4. (unknown) + noise")
    section_noise(data)
    print("\n## 5. Quote coverage (column-aware)")
    section_quotes(data)


# Articles/prepositions that carry no figure identity — dropped before token comparison.
_STOP = {
    "di", "del", "della", "dello", "dei", "degli", "delle", "dell",
    "che", "con", "la", "il", "lo", "le", "i", "gli", "un", "una", "uno",
    "e", "ed", "o", "a", "ad", "da", "in", "su", "per", "tra", "fra", "l", "d", "se",
}


def content_tokens(label):
    """The figure-bearing tokens of a label (case-folded, ≥2 chars, no article/preposition).
    `Maestro Adamo` -> {maestro, adamo}; `l'anima` -> {anima}; used for near-dupe linking."""
    return frozenset(
        t for t in (w.casefold() for w in _WORD_RE.findall(label))
        if len(t) >= 2 and t not in _STOP
    )


def build_nodes(label_count):
    """The deterministic code-merge the registry performs: fold_key -> (canonical, total).
    Canonical is the most frequent original spelling in the group. This
    is what 2923 distinct labels collapse to BEFORE any LLM touches them."""
    groups = defaultdict(list)
    for nl, n in label_count.items():
        groups[fold_key(nl)].append((nl, n))
    nodes = {}
    for key, items in groups.items():
        canonical = max(items, key=lambda x: (x[1], x[0]))[0]
        nodes[key] = (canonical, sum(n for _l, n in items))
    return nodes


def near_dupe_pairs(nodes):
    """Ordered (shorter, longer) node pairs where the shorter's content-token set is a proper
    subset of the longer's (`Virgilio` ⊂ `quel Virgilio`, `Adamo` ⊂ `Maestro Adamo`) — a figure
    the longer node likely extends, that fold_key could not merge. SET labels (commas) are
    excluded; NOT transitively chained (so a common head like `anima` does not collapse hundreds
    of nodes into one blob). A fuzzy human-inspection signal, not an auto-merge."""
    canon = [c for (c, _n) in nodes.values() if "," not in c]
    toks = {c: content_tokens(c) for c in canon}
    rich = [(c, toks[c]) for c in canon if toks[c]]
    pairs = []
    for a, ta in rich:
        for b, tb in rich:
            if a != b and ta < tb:
                pairs.append((a, b))
    return pairs


def epithet_nodes(label_count):
    """Registry NODES (post-fold_key) that are descriptive epithets, not proper names, and
    occur ≥2× — the candidate list the per-canticle epithet-grouping LLM call must hold
    (the registry build). Computed on nodes, so `il Sole`/`la Fortuna` (already folded onto their
    bare form) do NOT inflate it. Sizes the binding decision gate."""
    nodes = build_nodes(label_count)
    out = []
    for canonical, total in nodes.values():
        if total < 2 or canonical == UNKNOWN:
            continue
        if "," in canonical:  # a set, handled by split_set not epithet grouping
            continue
        if _is_cap_name(canonical):
            continue
        out.append((canonical, total))
    return sorted(out, key=lambda kv: -kv[1])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to measure (default: all three)")
    args = ap.parse_args()

    datasets = []
    for canticle in args.canticles:
        if not committed_cantos(canticle):
            print(f"(skip {canticle}: no committed 04-tags)", file=sys.stderr)
            continue
        data = CanticleData(canticle)
        datasets.append(data)
        report(data)

    if not datasets:
        print("No committed 04-tags found.", file=sys.stderr)
        sys.exit(1)

    # ---- global totals + decision gates (registry is decided globally) ----
    global_count = Counter()
    global_unknowns = global_noise = global_spans = 0
    global_buckets = Counter()
    for d in datasets:
        global_count.update(d.label_count)
        global_unknowns += len(d.unknowns)
        global_noise += len(d.noise)
        global_spans += d.spans_total
        global_buckets.update(d.span_buckets)

    distinct = set(global_count)
    fold_collisions = fold_groups(distinct)               # code-merged by fold_key
    nodes = build_nodes(global_count)                     # the registry's node set
    merged_labels = sum(len(v) for v in fold_collisions.values())
    near_dupes = near_dupe_pairs(nodes)                   # residual fold_key could NOT merge
    shorter_extended = len({a for a, _b in near_dupes})   # distinct figures with a longer form
    global_sets = [(nl, split_set(nl, distinct)) for nl in distinct
                   if "," in nl and split_set(nl, distinct)]
    epithets = epithet_nodes(global_count)

    print(f"\n{'=' * 70}\n# GLOBAL totals (all canticles)\n{'=' * 70}")
    print(f"  tag lines: {sum(global_count.values())}")
    print(f"  distinct labels: {len(distinct)}")
    print(f"  fold_key code-merge: {len(distinct)} labels -> {len(nodes)} nodes "
          f"({len(fold_collisions)} groups merge {merged_labels} labels)")
    print(f"  residual near-dupe subset pairs (fold_key MISSED): {len(near_dupes)} "
          f"over {shorter_extended} base figures (fuzzy, human-inspection)")
    print(f"  confirmed sets: {len(global_sets)}")
    print(f"  epithet nodes occurring ≥2× (per-canticle gate input): {len(epithets)} global")
    print(f"  (unknown): {global_unknowns}    no-lexical-anchor labels: {global_noise} "
          f"(weak signal — readings are English, so Italian names over-flag)")
    print(f"  quote spans: {global_spans}  buckets: " +
          ", ".join(f"{b}={global_buckets.get(b,0)}"
                    for b in ("strong-unique", "multi-strong", "weak-only", "plural-only", "none")))

    # per-canticle epithet-node counts: the epithet-grouping call is ONE per canticle (Step 4),
    # so the gate is per-canticle, not global.
    per_canticle_epithets = {d.canticle: len(epithet_nodes(d.label_count)) for d in datasets}

    print(f"\n## Decision gates")
    print(f"  fold_key handles variant merging in CODE; the LLM residual is (a) typing every")
    print(f"  node, (b) grouping epithet nodes per canticle. The gates size (b) and the leftover")
    print(f"  near-dupes (a) code can't merge.")
    g1 = shorter_extended < 50
    worst_canticle = max(per_canticle_epithets, key=per_canticle_epithets.get)
    worst = per_canticle_epithets[worst_canticle]
    g2 = worst < 150
    print(f"  [{'PASS' if g1 else 'FAIL'}] base figures with longer forms < 50:   {shorter_extended} "
          f"(fuzzy gate)")
    print(f"  [{'PASS' if g2 else 'FAIL'}] epithet nodes/canticle < 150:          " +
          ", ".join(f"{c}={n}" for c, n in per_canticle_epithets.items()) +
          f"  (worst: {worst_canticle} {worst})")
    if g1 and g2:
        print(f"  => LLM residual: ONE batched typing + per-canticle epithet-grouping step")
    else:
        print(f"  => LLM residual: REVISIT — gate failed; epithet grouping likely needs")
        print(f"     batching/sub-passing rather than one call per canticle (see report body)")


if __name__ == "__main__":
    main()
