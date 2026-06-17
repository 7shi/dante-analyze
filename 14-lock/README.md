# 14-lock — the translation context lock

The last pass of the context-lock direction (repository `PLAN.md` direction 1). Pure code, no LLM.

`14-lock` joins the five committed context-lock layers plus the assembled knowledge graph into a
per-scene **identity-and-setting record** — what a translation or digest must not get wrong: where
the scene is set, which class of souls dwells there, who is present versus merely mentioned, who
speaks and is addressed, which referring expressions resolve to which figure, and the literal and
simile relations among them. Identity and setting **only** — never the source's meaning or a
paraphrase. Each scene carries its line range as the verifiable `basis` anchor.

This is the setting layer the KG (`08-kg`) does not carry — `08-kg` is action-only (who-does-what
edges); it has no location, region, or cohort, because those are narrative *state*, not actions.
The lock supplies that layer and folds in the KG's resolved figures and relations, per scene.

## What it reads

All through the `dante_analyze` `load_*` public API only (no cross-pass imports):

| Layer | Loader | Used for |
|---|---|---|
| `01-scenes` | `load_scenes` | the canonical scene segmentation `(s, e)` + titles |
| `09-location` | `load_locations` | per-scene primary current setting (`location`) |
| `10-topography` | `load_topography` | the canonical `region` a scene belongs to (via its runs) |
| `11-presence` | `load_presence` | `cast`: who is present vs merely mentioned |
| `12-addressee` | `load_addressee` | per speech span: `speaker` + `addressee` |
| `13-cohort` | `load_cohort` | `cohort`: which soul-class(es) dwell in the scene |
| `08-kg` | `load_kg` | resolved edges → `refer` / `relations` / `simile` per scene |

Every per-scene layer is keyed to the same `(s, e)` segmentation, so the join is a deterministic
gather; KG edges carry their own scene, so they filter to a scene by equality.

## What it writes

`14-lock/<canticle>/NN.toml`, one per canto, with one `[[scene]]` table per scene:

```toml
canticle = "inferno"
canto = 1

[[scene]]
lines = "61-66"
title = "A Shadow in the Desert"
location = "basso loco"          # 09-location primary current setting
region = "là dove 'l sol tace"   # 10-topography region containing the scene
cast = [
  { who = "Dante", status = "present" },
  { who = "Virgilio", status = "present" },
]
speech = [                       # one per attributed 12-addressee span (cross-scene quotes allowed)
  { quote_id = "1:65", lines = "65-65", speaker = "Dante", addressee = "Virgilio", source = "code" },
]
relations = [                    # KG literal-frame edges in the scene
  { subj = "Dante", predicate = "sees", obj = "Virgilio", lines = "62-62" },
]
basis = "61-66"
```

- `lines`, `title`, `location`, `region`, `cast`, and `basis` are always present (`cast` may be `[]`).
- `cohort`, `speech`, `refer`, `relations`, `simile` appear only when non-empty.
- Names are **source spelling** (`Virgilio`, matching the KG nodes); anglicization belongs to the
  downstream glossary, not here.
- `speech` is an **array** (not a scalar `speaker`/`addressee`): an `01-scenes` scene can hold
  several speech spans, so per-span entries are kept lossless. This refines the single-speaker
  `ref/inferno-01.toml` sketch.

TOML is written by a small hand-rolled renderer (`render_toml`), since Python has no stdlib TOML
writer; the layout mirrors `ref/inferno-01.toml`'s readable inline-table style. `load_lock` reads
it back with `tomllib` (falling back to `tomli` before Python 3.11).

## Field derivation

- `location` — the first concrete `it` of `09-location`; when a scene only marks a carry (`-`), the
  previous scene's setting carries forward.
- `region` — the unique `10-topography` region whose run in this canto contains the scene.
- `cast` — every `11-presence` figure as `{who, status}` (`present` | `mentioned`).
- `speech` — every attributed `12-addressee` span keyed to this scene.
- `cohort` — the `13-cohort` soul-class labels.
- `refer` — KG edge ends whose surface label resolved to a **differently-spelled** canonical node
  (`name != node`): the identity a translation must not take from the surface form alone. Deduped.
- `relations` / `simile` — KG `literal` / `simile` frame edges in the scene, deduped. `simile`
  records the `vehicle` (the edge object).

`note` prose and `misnames-*` flags from the `ref` sketch are deliberately out of scope (identity
only); see repository `PLAN.md`.

## Checks

Structural, code-only, fail-loud — a problem skips the whole canticle's write, exactly as `08-kg`
does:

- every scene of the canto gets exactly one lock entry (the per-scene layers cover the scene set);
- every scene resolves to exactly one topography region (the runs are total);
- every basis / cited line range falls inside its scene (a cross-scene quote span is checked on its
  start line, since `12-addressee` keys a span by the scene holding its start).

All 100 cantos pass.

## How to run

```bash
make -C 14-lock                       # build all three canticles
make -C 14-lock clean                 # remove the generated locks
uv run dante-analyze lock show inferno 1   # inspect one canto
```

## Measured results

| canticle | cantos | scene locks | speech | cohort | refer | relations | simile |
|---|--:|--:|--:|--:|--:|--:|--:|
| inferno | 34 | 588 | 203 | 217 | 152 | 1210 | 77 |
| purgatorio | 33 | 616 | 187 | 184 | 150 | 1099 | 90 |
| paradiso | 33 | 592 | 98 | 96 | 117 | 702 | 85 |
| **total** | **100** | **1796** | **488** | **497** | **419** | **3011** | **252** |

Structural comparison against the hand-written `ref/inferno-01.toml`: the generated Inferno 1 lock
has the **same 20 scenes with identical line ranges**, and `location` / `cast` / `simile` align
scene-by-scene. Two faithful-by-design differences (not defects — the committed layers, not
hand-curation, are the source):

- the sketch's `refer` is hand-curated periphrasis-meaning glosses ("il pianeta" = the sun) carrying
  `note` prose; those are out of scope here, so the code-derived `refer` (surface≠canonical folds
  only) is sparser — 0 in Inferno 1, 419 canticle-wide where surfaces genuinely diverge from the
  canonical node;
- where one quote runs across several scenes, only the scene holding its start carries a `speech`
  entry (the sketch repeats the speaker across continuation scenes).
