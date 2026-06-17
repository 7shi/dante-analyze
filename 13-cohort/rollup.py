#!/usr/bin/env python
"""
Cohort rollup — the canonical region view (pure code, no model).

cohort.py judges the cohort per SCENE (the unit the lock consumes). This script folds those per-scene
cohorts onto the canonical REGIONS of 10-topography, the place analogue of 05-registry's canonical
view: for each region, the soul-classes its scenes resolve to, with the number of scenes backing
each. It mirrors 10-topography's own render (one block per region in journey order) and makes no
judgment — every cohort is already a checked, canonical class/generic label from cohort.py.

A scene (canto, s, e) belongs to the region whose 10-topography run in that canto contains its start
line (the runs partition every scene, so the assignment is total).

Input:  13-cohort/<canticle>/NN.txt  (per-scene cohorts; run cohort.py first)
        10-topography/<canticle>.txt (regions)
Output: 13-cohort/<canticle>.txt     (committed; per region its cohort soul-classes)
"""
import argparse
import sys
from collections import Counter, OrderedDict

from dante_analyze import (
    COHORT_DIR, available_cantos, load_cohort, load_topography, fold_key,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")


def region_runs_by_canto(topo):
    """{canto: [(ls, le, region_id), …]} from a loaded topography, for scene -> region lookup."""
    by_canto = {}
    for region_id, region in topo.items():
        for (canto, ls, le) in region["runs"]:
            by_canto.setdefault(canto, []).append((ls, le, region_id))
    return by_canto


def aggregate(canticle):
    """{region_id: Counter(canonical_label -> scene count)} plus a fold_key -> canonical-label map,
    folding every per-scene cohort onto its region."""
    topo = load_topography(canticle)
    by_canto = region_runs_by_canto(topo)
    counts = {region_id: Counter() for region_id in topo}
    label_of = {}   # fold_key -> first-seen canonical label (cohorts are already canonical)

    for canto in available_cantos(canticle):
        if canto not in by_canto:
            continue
        runs = by_canto[canto]
        for (s, e), cohorts in load_cohort(canticle, canto).items():
            region_id = next((rid for ls, le, rid in runs if ls <= s <= le), None)
            if region_id is None:
                continue
            for c in cohorts:
                key = fold_key(c["cohort"])
                label_of.setdefault(key, c["cohort"])
                counts[region_id][key] += 1
    return topo, counts, label_of


def render(canticle, topo, counts, label_of):
    parts = [f"# Cohort — {canticle}\n"]
    for region_id, region in topo.items():
        c = counts[region_id]
        if c:
            ordered = sorted(c, key=lambda k: (-c[k], label_of[k].lower()))
            cohort_str = ", ".join(f"{label_of[k]} ({c[k]})" for k in ordered)
        else:
            cohort_str = "(none)"
        parts.append(f"## {region_id}\n- en: {region['en']}\n- cohort: {cohort_str}\n")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description="Cohort rollup: fold per-scene cohorts onto the "
                                             "10-topography regions (pure code, no model).")
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES))
    args = ap.parse_args()

    for canticle in args.canticles:
        if not available_cantos(canticle):
            print(f"(skip {canticle}: no committed inputs)", file=sys.stderr)
            continue
        topo, counts, label_of = aggregate(canticle)
        path = COHORT_DIR / f"{canticle}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(canticle, topo, counts, label_of), encoding="utf-8")
        n_named = sum(1 for rid in topo if counts[rid])
        print(f"cohort rollup {canticle}: {n_named}/{len(topo)} regions have a cohort -> {path}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
