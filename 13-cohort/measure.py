#!/usr/bin/env python
"""
Measure the cohort residual BEFORE building / running the LLM pass (code only, no model).

13-cohort judges, per SCENE, which class of souls dwells there. The closed candidate set is the
scene's present class/generic figures (11-presence + 05-registry), reader-apostrophes dropped — see
cohort.py:scene_candidates. The decision splits by candidate count: 0 -> (none), 1 -> code,
>=2 -> the LLM residual. This script tabulates that split per canticle so the candidate definition
can be validated and the LLM workload sized first. It does NOT call the model.

Run:  uv run 13-cohort/measure.py [canticle ...]   (default: all three)
"""
import argparse
import sys
from collections import Counter

from dante_analyze import available_cantos, load_scenes, load_presence, load_registry

from cohort import scene_candidates

CANTICLES = ("inferno", "purgatorio", "paradiso")


def measure(canticle):
    registry = load_registry(canticle)
    buckets = Counter()       # none / code / llm scenes
    multi = Counter()         # how many >=2-candidate scenes, by candidate-set size
    big = []                  # scenes with the largest candidate sets (sanity check)

    for canto in available_cantos(canticle):
        _, scenes = load_scenes(canticle, canto)
        presence = load_presence(canticle, canto)
        for s, e, name in scenes:
            cands = scene_candidates(presence.get((s, e), []), registry)
            n = len(cands)
            buckets["none" if n == 0 else "code" if n == 1 else "llm"] += 1
            if n >= 2:
                multi[n] += 1
                big.append((n, canto, s, e, name, [c["who"] for c in cands]))

    n_scenes = sum(buckets.values())
    print(f"\n===== {canticle}: {n_scenes} scenes =====")
    print(f"  candidate count   0 -> (none): {buckets['none']:3d}    "
          f"1 -> code: {buckets['code']:3d}    >=2 -> llm: {buckets['llm']:3d}")
    if multi:
        sizes = sorted(multi)
        print(f"  residual scene candidate-set sizes: "
              f"{', '.join(f'{k}:{multi[k]}' for k in sizes)} (max {sizes[-1]})")
    for n, canto, s, e, name, who in sorted(big, reverse=True)[:5]:
        print(f"    largest: {canto}:{s}-{e} ({name}) [{n}] {who}")
    return buckets


def main():
    ap = argparse.ArgumentParser(description="Measure the 13-cohort per-scene residual (code only).")
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES))
    args = ap.parse_args()

    totals = Counter()
    for canticle in args.canticles:
        if not available_cantos(canticle):
            print(f"(skip {canticle}: no committed inputs)", file=sys.stderr)
            continue
        totals.update(measure(canticle))
    print(f"\n===== totals =====")
    print(f"  (none): {totals['none']}    code: {totals['code']}    llm (residual): {totals['llm']}")


if __name__ == "__main__":
    main()
