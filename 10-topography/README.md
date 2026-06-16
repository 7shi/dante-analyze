# 10-topography — canonical regions (context-lock Step 2)

The place analogue of `05-registry`. `09-location` emits, per scene, the current-setting **surface**
the source uses (`it`) — deliberately noisy: across 100 cantos, 371 place-naming lines use 337
distinct surfaces. This pass folds those surfaces into a small set of canonical **regions** and
assigns one region per scene, a **piecewise-constant region sequence** — the macro where-layer the
action-only KG (`08-kg`) lacks. It fixes setting structure only; per the repository premise the pass
names no circle / terrace / sphere, so the poem's known geography stays an **evaluation** target, not
an input.

## How it works

The journey is (almost) monotonic, so region identity is **positional**: a `ripa` in Inferno 4 is
not the `ripa` in Inferno 31. The pass therefore **walks each canticle in journey order** rather than
clustering surfaces globally — a global cluster, blind to position, merges far-apart places that
share a generic word (`ripa`, `lago`, `fosso`, `cielo`) and breaks the sequence.

Per canto, one narrow LLM judgment marks a **boundary**: reading the canto's named place-terms in
order, each term either continues the **same** stretch as the term above it or begins a **new** one
(term 1 continues the region the canto opens in, or begins a new one). Because every comparison is
only against the *current* region, a later canto can never be merged back into an earlier one — the
region sequence is **piecewise-constant by construction**, so recurrence is impossible.

**Naming is code, not the model** (the `05-registry` split: deterministic merge, model residual).
The model only marks `same`/`new`; code names each region from its member surfaces — the most
frequent, ties broken by earliest appearance — and disambiguates a shared label in journey order
(`lo scoglio`, `lo scoglio #2`). So no coined or unrepresentative label can leak in.

Chain-of-thought is **off**: the judgment is a short, checkable per-term label; CoT only made the
local model deliberate to the point of runaway without improving the call.

Pipeline (all but the boundary is deterministic code):

1. **terms** — `canto_terms`: the canto's named `it` place-terms in journey order, plus which scene
   names a place versus carries the setting forward.
2. **boundary (LLM, cached)** — `walk_canto` marks each term `same`/`new` given the currently
   occupied region; in-conversation retry. The `Walk` accumulates region members and keys in order.
3. **name + sequence + render** — code labels each region (`Walk.label`); `build_sequence` assigns a
   region per scene (carry-forward across scenes and cantos); `build_runs` merges into runs.

## Inputs / outputs

```
Input:  09-location/<canticle>/NN.txt   (committed; run 09-location/location.py first)
Output: 10-topography/<canticle>.txt            the region registry + sequence
        10-topography/<canticle>.clusters.txt   resume cache (per-canto, replays deterministically)
```

Regions are per-canticle (each canticle is its own journey), so the walk and its cache are
per-canticle. The cache line `<canto>:<occ> <surface> = <region-key>` lets an interrupted run resume
at canto granularity and re-render with **no** LLM calls. Read the output downstream with
`load_topography(canticle)` (in `dante_analyze.checkpoint`) → `{region_id: {en, surfaces, runs}}`,
where `runs` are `(canto, ls, le)` source-line spans; a scene `(canto, s, e)` belongs to the region
whose run in that canto contains it.

### Region block

```
## là dove 'l sol tace
- en: where the sun is silent
- surfaces: là dove 'l sol tace (1), basso loco (1), gran diserto (1), loco selvaggio (1), ...
- runs: 1:61-136, 2:1-142
```

- heading — the canonical region label (a representative source surface), unique per file;
- `en` — its English gloss (from the label surface's `09-location` gloss);
- `surfaces` — the source place-terms folded into the region, with counts;
- `runs` — the contiguous source-line spans the region covers, in journey order.

## Structural check

- **Fatal:** every named term has a region (the per-scene sequence is then total — every scene maps
  to exactly one region).
- **Soft (warning, kept):** a region recurring after another intervenes. The walk is
  piecewise-constant by construction, so this should never fire; if it does, it flags a real anomaly.

Whether a boundary is placed at the *right* line is interpretation, shipped as generated — no
hand-proofreading (improve the method and re-measure instead).

## Run

```bash
uv run 10-topography/topography.py inferno [-m MODEL]
make -C 10-topography        # all three canticles
```

The `<canticle>.txt` is the committed output; delete the `.clusters.txt` cache to re-walk from
scratch. Model: `ollama:gemma4:31b-it-qat` by default; the build was produced with a Gemma-4-31B
cloud endpoint (`-m`).

## Measured result

Full build, all 100 cantos (`371` place-terms → `91` regions), every region sequence total and
contiguous:

| canticle | scenes | place-terms | regions | of which `same` | LLM calls |
|---|---|---|---|---|---|
| inferno    | 588 | 196 | 47 | 141 | 34 |
| purgatorio | 616 | 117 | 36 |  78 | 27 |
| paradiso   | 592 |  58 |  8 |  51 | 26 |

- **Piecewise-constant holds:** `0` recurring regions and `0` mis-covered scenes in all three
  canticles — the structural goal the positional walk was built for.
- **The text names its own structure.** With no canon supplied, the region labels surface the poem's
  *own* division words: Inferno's `primo cerchio`, `la quarta lacca`, `ripa sesta`,
  `l'ottava bolgia`, the Cocytus zones (`l'Antenora`, `Tolomea`); Purgatorio's `prima cornice`,
  `quinto giro`, `purgatorio`; Paradiso's `secondo regno`, `temprata stella sesta`,
  `settimo splendore`. Recovering the known structure from the source alone is the evaluation payoff.
- **Granularity tracks how concretely each canticle names place** (not tuned): Inferno is finest (47
  regions over its concrete terrain, finer than its 9 circles), Paradiso coarsest (8 regions — its
  setting is named abstractly as light and spheres, so long runs of `same` collapse many cantos).

Spotlight on **Inferno 1** (the hand-written reference lock, `ref/inferno-01.toml`): the walk yields
three regions — `selva oscura` (1-12), `piè d'un colle` (13-60, folding `la piaggia diserta` and
`cominciar de l'erta`), `là dove 'l sol tace` (61-136, the `basso loco` / `gran diserto`). This
matches the reference's progression structurally — dark wood → foot of the hill/slope → the dark low
place, no circle and no sinners — differing only in name form (source spelling here, anglicized in
the reference) and one boundary placed a few lines apart. Structural agreement, not string-exact, is
the bar (per the name-form difference).

## Notes

- `load_topography` and its parse live in `dante_analyze/checkpoint.py`, beside `load_locations` —
  reused parsing belongs in the package, not in a pass script.
- The same/new boundary is the place analogue of the present-cast vs named-but-absent split in the
  person pipeline; cohort (which class of souls inhabits a region) is a distinct judgment deferred to
  its own later pass, to keep one judgment per script.
