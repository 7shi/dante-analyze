# Node identity — open problems

> **Scope.** The identity-resolution *mechanism* lives where it is used, not here: Fix 1 (deterministic
> alias merge) and Fix 2 (per-tag coreference overlay) in `05-registry/README.md` ("Identity resolution
> beyond fold_key"); the `deictic` type and the individual+collective bundle split in `04-tags/README.md`
> (typing), `05-registry/README.md`, `ARCHITECTURE.md`, and the `11-presence` / `13-cohort` READMEs.
> Other deferred quality work (pronoun-layer marking, diff-only storage, digest follow-ups) lives in
> `PLAN.md` §2 "Deferred quality work". **This document tracks the one remaining open problem below.**

## Open problem — no granular invalidation

A correct node set is necessary but its propagation is **not free**. The passes that consume identity
are spread across the pipeline, some cache their LLM output, and there is **no granular
invalidation** — a node-set change does not automatically re-run the passes that depended on the old
identities, and the LLM passes that cache finished scenes will **silently skip** the ones that changed.
The safe fallback is a full clean (`make clean && make` across 11→15), which regenerates all 100 cantos
and is always correct but coarse.

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

### Feasibility (assessed, not yet built)

A targeted invalidator is **feasible and structurally easy** — not a research problem, roughly a
single helper script. The key enabler is the output layout: each caching pass stores **one file per
canto** (`11-presence/<canticle>/NN.txt`, etc.) and derives its resume set *from that file itself*
(`done_scene_ends(path)` reads the scene-ends already present in the canto's own output — the
checkpoint **is** the cache, there is no separate opaque cache to surgically edit). So invalidating a
canto is just `rm <pass>/<canticle>/NN.txt`; the existing resume regenerates only the missing cantos.
The pipeline is already canto-granular by construction.

Three mechanical ingredients, all deterministic (no LLM):

1. **Touched-canto computation.** A coreference-overlay edit is a `coref.txt` diff whose keys already
   carry `canticle/canto/s/e`, so the touched cantos fall out directly; a typing/registry change is a
   `types.txt` / node-set diff joined through the tags to the cantos where the changed nodes appear.
2. **Invalidation = file delete.** `rm` the per-canto checkpoint for each touched canto in each
   affected pass.
3. **Dependency fan-out.** A small fixed graph (`registry → 11/13`, `11 → 12`, `14 → 15`): a canto
   invalidated upstream propagates to its downstream passes.

**The one real risk is under-invalidation (completeness), not difficulty.** A merge can affect a
canto whose text never contains the changed label but whose roster/addressee referenced it
transitively; if the touched set misses it, that canto is **silently stale** — strictly worse than a
full clean, which is always correct. So the touched-canto computation must be **conservative
(over-include)**, and the safe fallback (`make clean`) must stay the documented escape hatch.

**Why it stays deferred:** the full-clean fallback is always correct, so this is a pure cost
optimization. It becomes worth building only if node-set changes become frequent enough that
regenerating all 100 cantos per change is the dominant cost. Effort is small (≈ a day); priority is
low until rebuild frequency justifies it.
