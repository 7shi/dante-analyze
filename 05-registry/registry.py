#!/usr/bin/env python
"""
Registry build — Step 1 of the knowledge graph. PURE CODE (no model call).

Aggregates the per-scene 04-tags labels into one canonical, source-spelled NODE per figure across
the whole work, with node typing (closed vocabulary), set support, and a per-canticle alias-surface
inventory. This is the node layer the speech/relations passes join onto.

Pipeline: gather (code) -> fold-merge (code) -> alias-merge (code) -> set-resolve (code) ->
render per-canticle (code) -> structural check (code). The fold (`Nodes`) is shared with
`04-tags/node_types.py`; the node TYPES are read from `04-tags/types.txt` (`load_types_cache`), produced
by that step — not generated here. So the build is the last link of the linear identity chain
`tags.py -> node_types.py -> coreference.py -> registry.py`, reading 04-tags only, with no back-edge.

The deterministic code-merge collapses the distinct labels by `fold_key` (canonical = most frequent
original spelling, decided GLOBALLY so a cross-canticle figure shares one label); `measure.py`
already proved this is total and sizes it (2,923 distinct -> 2,712 nodes).

Decision: epithet grouping is SKIPPED in v1 — every epithet node
stays its own node, flagged `grouped: no`. A flagged singleton is safer than an unverifiable merge;
consolidation is a later pass.

Output `05-registry/<canticle>.txt` (committed). Surfaces and labels are PER-CANTICLE (each file is
self-contained, so the structural check closes within it); the canonical label and type are global,
re-emitted in each canticle file the node appears in. `Nodes` gathers WITH the coreference overlay
applied (`load_tags` default), so the render reflects the Fix-2 merges.

Input:  04-tags/<canticle>/NN.txt   (committed; run 04-tags/tags.py first)
        04-tags/types.txt           (typing cache; run 04-tags/node_types.py first)
        02-markup/<canticle>/NN.txt (for number_scene's surface meta)
Output: 05-registry/<canticle>.txt  (committed)
"""
import argparse
import sys
from collections import Counter

from dante_analyze import (
    REGISTRY_DIR,
    norm_label, fold_key, is_capitalized_name,
    Nodes, TYPES,
    load_aliases, load_types_cache, ALIASES_FILE,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")


# ---------- 2b. alias merge (pure code) ----------

def apply_aliases(nodes, pairs):
    """Merge alias nodes into their canonical targets in-place."""
    for alias, canonical in pairs:
        alias_key = fold_key(norm_label(alias))
        canonical_key = fold_key(norm_label(canonical))
        if alias_key not in nodes.labels:
            raise ValueError(f"alias '{alias}' (key '{alias_key}') not found in nodes")
        if canonical_key not in nodes.labels:
            raise ValueError(f"canonical '{canonical}' (key '{canonical_key}') not found in nodes")
        nodes.labels[canonical_key].update(nodes.labels.pop(alias_key))
        for c, counter in nodes.labels_canticle.pop(alias_key).items():
            nodes.labels_canticle[canonical_key][c].update(counter)
        for c, counter in nodes.surfaces.pop(alias_key).items():
            nodes.surfaces[canonical_key][c].update(counter)
        print(f"alias-merge: '{alias}' -> '{canonical}'", file=sys.stderr)


# ---------- 3. node typing (read the cache; produced by 04-tags/node_types.py) ----------

def load_types(nodes):
    """The {canonical: type} cache (04-tags/types.txt), checked complete against `nodes`: every
    non-set canonical must be typed. types.txt is built overlay-free, so it is a superset of every
    label; a miss means typing has not been run — fail loudly rather than render `(untyped)` nodes."""
    cache = load_types_cache()
    missing = sorted(nodes.canonical(key) for key in nodes.labels
                     if nodes.members(key) is None and nodes.canonical(key) not in cache)
    if missing:
        print(f"Error: {len(missing)} node(s) not typed in 04-tags/types.txt "
              f"(run 04-tags/node_types.py first); e.g. {', '.join(missing[:5])}", file=sys.stderr)
        sys.exit(1)
    return cache


# ---------- 4. render per-canticle (pure code) ----------

def render_node(nodes, key, canticle, types):
    """The `## <canonical>` block for a node as it appears in `canticle`."""
    canonical = nodes.canonical(key)
    members = nodes.members(key)
    lines = [f"## {canonical}"]
    if members is not None:
        lines.append("- type: set")
        lines.append(f"- members: {' | '.join(members)}")
        return "\n".join(lines)
    lines.append(f"- type: {types.get(canonical, '(untyped)')}")
    # per-canticle labels, canonical heading first, then others by descending count
    spellings = nodes.labels_canticle[key][canticle]
    others = sorted((s for s in spellings if s != canonical),
                    key=lambda s: (-spellings[s], s))
    labels = [canonical] + others   # global canonical heads the per-canticle spellings
    lines.append(f"- labels: {' | '.join(labels)}")
    surf = nodes.surfaces[key][canticle]
    surf_str = ", ".join(f"{s} ({n})" for s, n in
                         sorted(surf.items(), key=lambda kv: (-kv[1], kv[0])))
    lines.append(f"- surfaces: {surf_str}")
    if not is_capitalized_name(canonical):   # option A: epithet layer not consolidated
        lines.append("- grouped: no")
    return "\n".join(lines)


def render_canticle(nodes, canticle, types):
    parts = [f"# Registry — {canticle}\n"]
    for key in nodes.keys_in(canticle):
        parts.append(render_node(nodes, key, canticle, types) + "\n")
    return "\n".join(parts)


# ---------- 5. structural check (write time) ----------

def check_registry(nodes, canticle, types):
    """Problems with a rendered canticle (empty = OK): every distinct 04-tags label in the
    canticle assigned to exactly one node's labels
    (`(unknown)` already excluded); every set member resolves to a node; every type in
    vocabulary; canonical heading is one of its group's raw labels."""
    problems = []
    assigned = Counter()
    for key in nodes.keys_in(canticle):
        canonical = nodes.canonical(key)
        if canonical not in nodes.labels[key]:
            problems.append(f"{canonical}: heading not among its group's raw labels")
        for nl in nodes.labels_canticle[key][canticle]:
            assigned[nl] += 1
        members = nodes.members(key)
        if members is not None:
            # A member either folds onto a standalone node or is a bare capitalized name that
            # appears only inside the set (no own node) — split_set's admission contract. A
            # member that is neither would be a malformed set (a lowercase clause); flag it.
            for m in members:
                if fold_key(m) not in nodes.labels and not is_capitalized_name(m):
                    problems.append(f"{canonical}: set member '{m}' is not a node or a name")
        else:
            t = types.get(canonical, "(untyped)")
            if t not in TYPES:
                problems.append(f"{canonical}: type '{t}' not in vocabulary")
    for nl in nodes.distinct_canticle[canticle]:
        if assigned[nl] != 1:
            problems.append(f"label '{nl}' assigned to {assigned[nl]} nodes (expected 1)")
    return problems


# ---------- driver ----------

def main():
    ap = argparse.ArgumentParser(
        description="Registry build (Step 1): canonical node table over 04-tags, pure code "
                    "(typing comes from 04-tags/types.txt; see 05-registry/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to build (default: all three; canonical labels are global)")
    args = ap.parse_args()

    # canonical labels are decided globally — always gather all three so a cross-canticle
    # figure shares one label, even when only one canticle is being (re)rendered. Gather WITH the
    # coreference overlay applied (load_tags default) so the render reflects the Fix-2 merges.
    nodes = Nodes(CANTICLES)
    print(f"code-merge: {sum(len(c) for c in nodes.labels.values())} label spellings -> "
          f"{len(nodes.labels)} nodes", file=sys.stderr)

    aliases = load_aliases(ALIASES_FILE)
    if aliases:
        apply_aliases(nodes, aliases)
        print(f"alias-merge: {len(aliases)} pair(s) applied -> {len(nodes.labels)} nodes",
              file=sys.stderr)

    types = load_types(nodes)

    failed = False
    for canticle in args.canticles:
        if canticle not in nodes.distinct_canticle:
            print(f"(skip {canticle}: no committed 04-tags)", file=sys.stderr)
            continue
        problems = check_registry(nodes, canticle, types)
        if problems:
            failed = True
            print(f"\nregistry {canticle}: {len(problems)} STRUCTURAL problem(s):", file=sys.stderr)
            for p in problems:
                print(f"- {p}", file=sys.stderr)
            continue
        path = REGISTRY_DIR / f"{canticle}.txt"
        path.write_text(render_canticle(nodes, canticle, types), encoding="utf-8")
        n = len(nodes.keys_in(canticle))
        print(f"registry {canticle}: OK — {n} nodes written to {path}", file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
