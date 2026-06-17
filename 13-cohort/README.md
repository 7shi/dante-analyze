# 13-cohort — which class of souls dwells in each scene (context-lock Step 5)

The narrative-state analogue of `10-topography`. `10-topography` fixes *where* a scene is set; this
pass fixes *who resides there* — the **cohort**, the class of souls punished or rewarded in that
place (the lustful, the gluttons, the heretics, the blessed of a sphere …). The action-only KG
(`08-kg`) carries no such state, and the lock must not get the class of souls wrong (`../PLAN.md`,
`ref/PLAN.md`: `cohort | optional | wrong class of souls`). This pass supplies it as its own single
text-derived judgment, one judgment per script, so judgments never contaminate each other.

Everything is derived bottom-up from the source per the repository premise — no external list of
circles or terraces is ever an input; the poem's known geography is the *evaluation* target, not a
lookup table.

## How it works — code-first, LLM only for the residual

The `11`/`12` method: code resolves every unambiguous case, the LLM is invoked **only** on genuine
ambiguity. The judgment unit is the **scene** (the unit the lock consumes), not the region; see
"Why per scene" below. For each scene the closed candidate set is assembled entirely from resolved
upstream material (`cohort.py:scene_candidates`): the figures `11-presence` marks `present`, kept
only where `05-registry` types them `class` or `generic` (a collective of souls, not a named
individual), with a mechanical drop of 2nd-person reader-apostrophes (`lettor`/`lettore`/`lettori`),
deduped by `fold_key`. The candidate count alone decides the path:

- **0 candidates** → the `# (no soul-class present in this scene)` marker, no cohort line. Most
  scenes: narration, transitions, dialogue among named individuals only.
- **1 candidate** → that class, `source: code` (deterministic; basis = the present figure's basis).
- **≥2 candidates** → the LLM names which listed class(es) **reside** here, `source: llm`. Usually
  one; more than one is allowed when two soul-classes genuinely share a scene (a guardian class and
  the punished souls, the nine angelic orders of Paradiso 28). Guardians/wardens merely passing
  through, and the travellers, are the residual the model is the oracle for.

The LLM is thus confined to an oracle role — "which of these present collectives reside here" — over
a set the pipeline already fixed; everything else (gathering candidates, normalization, the
closed-set / geometry checks, resume) is code.

### The LLM path (ambiguous scenes only)

1. **Candidates (code).** Present cast ∩ class/generic by `fold_key` (the join `08-kg` uses), so a
   cosmetic spelling drift is tolerated and rendered back to the canonical registry label.
2. **Choose (LLM, one turn per scene).** The numbered scene source (`read_markup`), the region label,
   and the closed candidate list; the model returns the resident cohort(s) plus a `basis` line. CoT
   is **on** by default (`--no-think` disables): cohort is an interpretation-heavy reading, the
   reasoning runs in Ollama's thinking channel, `call_llm` caps runaway. Examples are schematic (the
   FORM only) — never a figure from the scene under test, so no answer leaks in.
3. **Check (code), retried in-conversation** (`check_cohort`):
   - **closed-set (fatal):** each named cohort is in the candidate set by `fold_key`, rendered back
     to the canonical label;
   - **no duplicate (fatal):** a class is named at most once;
   - **basis geometry (fatal):** the cited `basis` range lies within the scene's lines;
   - malformed lines are surfaced.

   Whether the reading is *correct* is interpretation, shipped as generated — no hand-proofreading
   (improve the method and re-measure instead).

## Why per scene (measured)

The approved initial plan judged cohort **per region**. `measure.py` (code only, all 100 cantos)
showed the per-region unit breaks down, so it was changed to per scene:

| unit | none | code | llm (residual) | residual candidate-set size |
|---|---|---|---|---|
| per region | 22 | 7 | 62 | up to ~35 (souls + guardians + sub-groups + apostrophes) |
| **per scene** | 1327 | 398 | **71** | **2–6** (max 6: Paradiso 28, the angelic hierarchy) |

A region spans many scenes, so its candidate set balloons and a pick from ~35 is far less checkable
than the small roster choices of `11`/`12`. Worse, where topography folds several terraces into one
region the cohort gets conflated. Per scene keeps each judgment a small closed-set choice and handles
within-region cohort changes naturally; `rollup.py` then builds the per-region view by code (see
"Rollup" below). The `cohort` field the lock consumes is per scene anyway.

## Inputs / outputs

```
Input:  02-markup/<canticle>/NN.txt    (source lines via read_markup), 01-scenes JSON (load_scenes),
        11-presence/<canticle>/NN.txt  (present cast = the candidate pool),
        05-registry/<canticle>.txt     (types: keep class/generic only),
        10-topography/<canticle>.txt   (regions, for the rollup only)
Output: 13-cohort/<canticle>/NN.txt    — per scene a `## Scene s-e: name` block of cohort lines
                                          (the file is the checkpoint: a finished scene is skipped on
                                          resume; delete to regenerate)
        13-cohort/<canticle>.txt       — per-region rollup, built by rollup.py (pure code, no model)
```

### Scene block

```
## Scene 25-36: The Infernal Tempest
- cohort: li spirti | source: code | basis: 32-36

## Scene 37-45: The Nature of the Sin
- cohort: i peccator carnali | source: code | basis: 38-45
```

- `cohort` — canonical registry label (source spelling, matching the KG nodes; per the `../PLAN.md`
  name-form rule);
- `source` — `code` | `llm`, how the cohort was decided;
- `basis` — the source line range supporting it (the present figure's basis for the code path, the
  LLM-cited line for the residual path; a line reference, so the checkable core is not a fragile
  string).

A scene with no class/generic present writes the `# (no soul-class present in this scene)` marker.

Read downstream with `load_cohort(canticle, canto)` → `{(s,e): [{cohort, source, basis_start,
basis_end}, …]}` (in `dante_analyze.checkpoint`, beside `load_presence`).

## Rollup — the canonical region view (pure code, no model)

`rollup.py` folds the per-scene cohorts onto the canonical regions of `10-topography`, the place
analogue of `05-registry`'s canonical view: for each region, the soul-classes its scenes resolve to
with a scene count, in journey order. A scene `(canto, s, e)` belongs to the region whose
`10-topography` run in that canto contains its start line. It makes no judgment — every cohort is
already a checked, canonical label — so it is safe to re-run any time. Output `13-cohort/<canticle>.txt`,
viewable with `dante-analyze cohort show <canticle>`. Where topography merges terraces, the rollup
shows the merge faithfully (purgatorio's `cornice` lists `i superbi`, `gli invidiosi`, … together
with their scene counts), which is exactly why the judgment itself is kept per scene.

## Run

```bash
uv run 13-cohort/cohort.py inferno [-c 1] [-m MODEL] [--no-think]
uv run 13-cohort/rollup.py inferno purgatorio paradiso   # code only, no model
make -C 13-cohort           # cohort.py (LLM) then rollup.py, all three canticles
make -C 13-cohort rollup     # the rollup step alone
uv run 13-cohort/measure.py inferno   # code-only residual tabulation (the table above)
```

**Parallel-safe by canticle:** `cohort.py`'s only write target is `13-cohort/<canticle>/NN.txt`, so
per-canticle runs write to disjoint subdirectories over read-only inputs and can run concurrently.

## Measured result

Full build, all 100 cantos — **1796** scenes, every cohort line passing the closed-set, no-duplicate
and basis-geometry check (`0` flagged across all `497` lines):

| canticle | cantos | scenes | none | code | llm | cohort lines (code / llm) |
|---|---|---|---|---|---|---|
| inferno    | 34 |  588 |  388 | 168 | 32 | 168 / 49 |
| purgatorio | 33 |  616 |  438 | 149 | 29 | 149 / 35 |
| paradiso   | 33 |  592 |  501 |  81 | 10 |  81 / 15 |
| **total**  |100 | 1796 | 1327 | 398 | 71 | 398 / 99 |

`none` / `code` / `llm` count the **scenes** taking each path (the candidate-count split *is* the
source split: 0 / exactly 1 / ≥2 candidates). The last column counts cohort **lines**: code scenes
emit one each (398), while the 71 llm scenes emit 99 lines because 24 of them name ≥2 resident
classes — the multi-cohort case the design admits.

- **Most scenes have no cohort.** 1327 of 1796 (73.9%) carry no class/generic at all — narration,
  travel, and exchanges among named individuals — and only 71 (4.0%) reach the oracle. Code carries
  the entire decided remainder (398 single-candidate scenes) with no LLM call. The residual is small
  and every pick is a closed-set choice, exactly the property `measure.py` was run to confirm before
  any model call.
- **The cohort thins from Inferno to Paradiso.** Inferno names a cohort in 200 / 588 scenes (34.0%) —
  its circles are crowded with the punished, collectively named (`anime prave`, `i peccator carnali`,
  `l'ombre`). Paradiso names one in just 91 / 592 (15.4%): the blessed appear as named individuals
  and lights far more than as sin-classes, so far fewer scenes offer a class/generic candidate.
- **The multi-cohort cases concentrate where classes genuinely share a scene.** Inferno has the most
  (14 scenes), Paradiso the fewest (4) — its largest being canto 28's nine angelic orders, the
  measured maximum candidate set of 6.

Spotlight on **Inferno 5** (the lustful): the storm scene resolves `li spirti` (`code`) and the
sin-naming scene `i peccator carnali` (`code`) — the carnal sinners, derived purely from the source,
matching the expected lustful cohort without any external geography fed in. The Minos judgment scene
resolves `anima mal nata` from the residual (`llm`).

## Notes

- `load_cohort` and `COHORT_LINE_RE` live in `dante_analyze/checkpoint.py`, beside `load_presence` —
  reused parsing belongs in the package, not in a pass script (ARCHITECTURE "Shared Code"; feedback
  memory `feedback_shared_library_reuse`).
- The rollup can surface upstream registry artifacts faithfully: e.g. a malformed `05-registry` entry
  that bundles an individual with a collective (`Dante, noble souls of Limbo`, typed `class`) flows
  through `11-presence` into a cohort line unchanged. That is a data-quality issue in `05-registry`,
  not a cohort defect — this pass consumes its inputs as given and does not hand-correct them.
- `14-lock` (the pure-code join of all layers plus the KG into the per-canto lock) is the next and
  final pass.
