# Node identity — open problems

> **Status.** The identity-resolution *mechanism* is complete and documented where it lives, not here:
> Fix 1 (deterministic alias merge) and Fix 2 (per-tag coreference overlay) in `05-registry/README.md`
> ("Identity resolution beyond fold_key"); the `deictic` type and the individual+collective bundle
> split in `04-tags/README.md` (typing), `05-registry/README.md`, `ARCHITECTURE.md`, and the
> `11-presence` / `13-cohort` READMEs. **This document tracks only the identity problems still open**,
> plus the propagation reality that makes any node-set change a coarse, manual rebuild.
>
> **Scope.** Node identity only; other deferred quality work (pronoun-layer marking, diff-only
> storage, digest follow-ups) lives in `PLAN.md` §2 "Deferred quality work".

## Why node identity matters

Two requirements drive the knowledge graph:

1. **Accurate character listing** — one node per actual figure, no duplicates, no phantom entries.
2. **Person-centric dynamics extraction** — querying a figure returns *all* of its edges, nothing
   silently missing.

Both depend on **node identity**. If one person is split across two nodes (bare `Guido` vs.
`Guido da Montefeltro`), the listing over-counts and a query on either node returns a partial view.
`04-tags` resolves each tag *per scene* and never cross-links tags across scenes; `fold_key` in the
registry merges only cosmetic drift (case, articles, elision); the identity layers on top (see Status)
close most of the rest.

## The constraint any identity fix must respect

Steps `06`–`08` and `11`/`13` join to the registry by `fold_key → canonical` (`raw_to_canonical`).
This map is **global**: it cannot route one surface form to two different nodes. So a per-tag identity
decision **cannot** be expressed as a registry edit — it must make the *label itself* identity-first,
applied at the one place every consumer reads tags (`load_tags`). Once labels are identity-first, the
existing join folds each tag onto the right node with **no change to the join or to 06/08/11**. Any
future identity work has to live at this layer (a `load_tags` overlay) or earlier (node construction /
typing), never as a downstream filter.

---

## Open problem 1 — epithet / periphrasis grouping (part A done; part B coref run in progress)

The registry over-counts `individual` nodes (vs. ~300–500 real named figures) from three sources, all
resolved at **node-construction time** (no downstream filter can remove them). Two are closed:
fragmentation (same figure, many labels) by the coreference overlay, and demonstrative labels
(`quel X`, `colui che …`, now typed `deictic`) plus individual+collective bundles (now split to sets).

The **third remains**: one-off epithets and governed periphrases that are *not* demonstrative-led —
`il Navarrese`, `la madre`, `l'angelo`, `l'anima della seconda fiamma` — stay their own `individual`
singleton nodes. The registry flags every non-name node `- grouped: no` and **defers consolidation to
a later pass** (`05-registry/registry.py`: "epithet grouping is SKIPPED in v1 — a flagged singleton is
safer than an unverifiable merge").

- **The flagged set is now clean (part A, done).** `is_capitalized_name` formerly mislabelled real
  titled names as epithets — `Tommaso d'Aquino`, `conte Ugolino`, `Francesco d'Assisi`,
  `Giacomo il Maggiore` — because it knew no lowercase honorific titles, elided-particle forms, or
  infix articles. It now recognizes all three (`dante_analyze/labels.py`), so 32 real names dropped
  their `grouped: no` flag. This is a **deterministic, node-set-preserving** change: the node keys,
  set membership, and types are byte-identical (verified) — only the registry `grouped:` diagnostic
  (unconsumed downstream) and three set-member surface inventories shift, so it triggers **no LLM
  rebuild**, just `make -C 05-registry`.
- **Scale of the genuine residual (part B, open).** After the name-test fix, **~245** non-name,
  non-`deictic` `individual` nodes remain flagged — these *are* genuine epithets/periphrases
  (`il Navarrese`, `la madre`, `l'imperador`, `la prima anima`), the real candidate set for grouping.
- **Impact.** These are **extra cast singletons, not misattributions** — each named figure is still
  correctly identified; the cost is an inflated character listing, not a corrupted edge.
- **Part B — the actual merge (code landed; coref run IN PROGRESS).** Referent resolution
  (epithet → named-figure) is interpretation with no structural check, so it is built as an extension
  of the coreference overlay (`04-tags/coreference.py`), not a deterministic test. For each genuine
  epithet, candidates are the **named individuals co-present in that scene** (`gather_epithet_scenes`);
  the model picks one or `distinct`, staged in `coref.txt` for human review exactly like the bare-name
  path. **Sizing (code-only):** 217 / 245 epithets have ≥1 co-present named candidate (~255 scene
  decisions), but the candidate sets are distractor-heavy and the poem often never names the figure,
  so `distinct` is expected to dominate — this is the "unverifiable merge" the project deliberately
  guards with human review, not a clean deterministic win like part A. The committed bare-name overlay
  is **unchanged** by the new code (regenerating `coref.txt` from the existing cache is byte-identical);
  the epithet decisions are new.
  - **Status: `make -C 04-tags coref` is running now** (the ~255 new epithet decisions; the cached
    bare-name scenes are skipped). When it finishes: review the new `coref.txt` lines, delete the
    wrong merges, commit the kept ones, then rebuild — `make -C 04-tags typing` is unaffected, so just
    `make -C 05-registry`, and the registry's `individual` over-count drops by however many epithets
    survived review. Same "fix upstream once, then rebuild" logic as the deictic/bundle fixes;
    **not a blocker** for the current rebuild.

---

## Open problem 2 — no granular invalidation

A correct node set is necessary but its propagation is **not free**. The passes that consume identity
are spread across the pipeline, some cache their LLM output, and there is **no granular
invalidation** — a node-set change does not automatically re-run the passes that depended on the old
identities, and the LLM passes that cache finished scenes will **silently skip** the ones that changed.

### How a node-set change reaches each pass

| Pass | Registry dependency | LLM / code | Auto-propagates on rerun? | Cache to clear |
|------|--------------------|-----------|--------------------------|----------------|
| 06-speech | direct (`raw_to_canonical`, `load_tags`) | code | **yes** (no cache) | — |
| 07-relations | transitive (cited `[n]` tags, joined via `load_tags` at 08) | LLM | **yes** (re-join at 08, code) | — |
| 08-kg | direct (`raw_to_canonical`, `load_tags`) | code | **yes** (no cache) | — |
| 09-location | none (source text only) | LLM | unaffected | `done_scene_ends` |
| 10-topography | none (09 surfaces only) | LLM | unaffected | `<canticle>.clusters.txt` |
| 11-presence | direct (type filter, set expand, `load_tags`) | LLM | partial | `done_scene_ends` |
| 12-addressee | transitive (via 11 roster) | LLM / code | partial | `done_scene_ends` |
| 13-cohort | direct (type filter) | LLM / code | partial | `done_scene_ends` |
| 14-lock | none (pure join of upstream) | code | **yes** | — |
| 15-digest | none (lock vocabulary) | LLM | follows 14 | `complete_scene_ends` |

**Two kinds of change propagate differently.** A change to the raw tag labels (a coreference overlay
edit) flows through `load_tags` and reaches every code consumer (06/08 + 07's edges re-joined at 08).
A change that only re-types or re-structures nodes (the typing / registry layer — e.g. the
`deictic`/bundle work) leaves `load_tags` byte-unchanged: 06-speech and 08-kg *edges* don't move, only
08-kg *node* files and the type-filtered LLM passes (11/13) do.

### Two findings this encodes

1. **Code passes propagate for free; LLM passes do not.** 06-speech, 08-kg, and 14-lock are pure code
   with no resume cache: rerun them and they reflect the new node set immediately (07-relations rides
   along — its edges cite per-scene `[n]` tag numbers, re-joined through `load_tags` at 08, so no 07
   rerun). Every pass that calls the model *for identity* caches finished scenes (`done_scene_ends` /
   `clusters.txt` / `complete_scene_ends`) and **silently skips** the scenes whose identities changed.
   Those need a **manual cache clear** for the affected cantos before rerun.
2. **11/13 are only partially affected.** A roster/cohort rename changes the figure the presence/cohort
   LLM was asked about, so those scenes genuinely need regeneration — but 13-cohort filters to
   `class`/`generic`, so a change confined to `individual` nodes rarely moves its candidate set.

### Rebuild order (after re-rendering the registry: `make -C 05-registry`)

```
06-speech, 08-kg        (code, no cache — just rerun; 08 re-joins 07's edges)
11-presence             (clear done_scene_ends for changed cantos, then rerun)
12-addressee, 13-cohort (depend on 11 / registry types; clear caches for changed cantos)
14-lock                 (code, no cache — rerun)
15-digest               (clear complete_scene_ends for changed cantos, then rerun)
```

09-location and 10-topography have **no registry dependency** and never need rebuilding for an identity
change. The cost is concentrated in the caching LLM passes (11, 12, 13, 15), and only for the cantos a
change actually touched.

**The open problem:** clearing only those cantos is **manual** today. A granular-invalidation
mechanism — record which cantos a node-set change touched and clear exactly those caches — would make
a rebuild incremental instead of coarse. Optional; it lowers rebuild cost, it does not affect
correctness.
