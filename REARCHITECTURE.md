# Re-architecture: an interpretation layer over a shared grammatical parse

## Context

The 15-pass pipeline (`OVERVIEW.md`) works end-to-end: source text → referent-resolved knowledge
graph → per-scene translation lock → bilingual digest. It was built as a "make something that
runs" stack, and it shows: the same scene is LLM-analyzed 3–4 times, and the grammatical knowledge
needed to do that is scattered ad hoc across passes ("屋上屋を重ねた").

Two things have changed the right shape of this project:

1. **The grammatical substrate now belongs upstream.** The corpus layer provides a shared,
   canon-neutral, checked **grammatical parse** of every line — tokens, morphology + lemma, an
   exhaustive noun-phrase enumeration, dependency / grammatical role, and a raw predicate-argument
   skeleton (noun-phrase ↔ verb tuples, with *no* frame, *no* coreference, *no* vocabulary
   normalization). That parse is reproducible and derived from the Italian alone. **This repo no
   longer re-reads raw text to recover who-is-syntactically-doing-what** — it consumes the parse.
2. **What is left is purely interpretive.** Stripped of the morphosyntax, `dante-analyze`'s real
   job is the small set of contested judgments the corpus deliberately does *not* make: *which
   noun phrases are entities and of what kind, which mentions corefer, which closed relation a
   predicate is, whether a clause is literal/simile/prophecy/reported, and which place is the
   scene's setting.* Everything else downstream (registry, graph, lock, digest) is a code-first
   derivation of those judgments.

In other words: the corpus answers *what does the grammar say?*; this repo answers *what does it
mean, in the poem's own terms?* — once, up front, and checkably.

**Intended outcome.** Replace the ladder's redundant re-reading with **one interpretive analysis
per scene** that sits on top of the corpus parse and resolves coreference, entity typing, relation
classification, and setting in a single checked artifact — then make every downstream layer a
code-first derivation of that single source of truth, with the model called only on a genuine
residual.

This plan is design-only. No implementation here.

---

## Target architecture

Four stages instead of fifteen ad hoc passes. The spine is unchanged in spirit — *the model
proposes; code checks, normalizes, joins, resumes* — but the model's proposal is now narrowly the
**interpretation** of an already-parsed scene, not a re-reading of raw text.

```
corpus parse ──────┐
   (given)         ▼
01-scenes ──> [A] Scene interpretation (per scene, LLM)  ── the only interpretive pass
 (partition)          │  reading (deliberation) → interpretive layer (checked)
                      │  entity typing + coref referents + relation/frame + setting
                      ▼
               [B] Consolidation (code-first, LLM on residual)
                      registry/entities · relation+speech graph · topography
                      ▼
               [C] Context lock (code-first, LLM on residual)
                      location · presence · addressee · cohort  → per-scene lock
                      ▼
               [D] Consumer
                      digest (+ code conformance proof)
```

### Stage A — scene interpretation (the one interpretive pass)

A single LLM conversation per scene, consuming the corpus parse **sliced by the `01-scenes`
partition** (the corpus is line-addressed; scene boundaries are this repo's, and `01-scenes`
survives as Stage A's second input) and producing the interpretive layer that the corpus
deliberately omits. It replaces `02-markup` + `03-reading` + `04-tags` +
`07-relations` (and absorbs the `coref.txt` overlay). Two turns, reusing the existing "split
deliberation from final output" rule:

- **Turn 1 — reading (deliberation).** Free prose "who does what, who speaks to whom", CoT on.
  This is today's `03-reading`, kept verbatim as the reasoning anchor and replayed as the assistant
  turn. Uncheckable by design; errors accepted as data (the Premise).
- **Turn 2 — interpretive layer (checked).** One artifact per scene that *annotates the corpus
  parse* rather than re-deriving it. Each facet attaches to ids the parse already provides:
  - **Entity typing**: for each corpus noun-phrase (the over-inclusive enumeration the corpus
    serves), decide whether it is an entity and assign its **kind** from a single closed,
    evidence-derived **entity-type vocabulary** (see below). Person and place are the two
    richly-developed kinds (the current effort); the person branch keeps the sub-kinds
    `{individual, generic, class, hypothetical-simile}`; `deictic` and `non-entity` remain
    cross-cutting markers. (subsumes the entity decision in `04-tags` + `09-location`'s place
    extraction — both fold into *one* typing of the shared NP list.)
  - **Coreference referents**: link each entity mention (name / epithet / pronoun / pro-drop
    subject — forms the corpus already distinguishes via morphology + role) to a scene-local
    **referent id** carrying its most-specific identity in source spelling, or `(unknown)`.
    A referent is an individual **or a set** with an explicit member list — plural first persons
    (`noi`, plural pro-drop) are the common case and resolve to their members where the reading
    determines them (this is what Stage B's `split_set` folds; distinct from any census-earned
    `group` kind for genuine collectives). Pronouns/pro-drop/epithets resolve *here*, up front.
    (subsumes `04-tags` + `coref.txt`.)
  - **Relation classification**: take each corpus predicate-argument skeleton tuple and add the
    interpretation the skeleton lacks — map the predicate onto the closed
    `measure.CLOSED_VOCAB ∪ {relates-to}`, attach a `frame ∈ {literal, simile, prophecy,
    reported}`, and rewrite the tuple's arguments from NP ids to **referent ids**. (subsumes
    `07-relations`; the *syntactic* tuple is given, only the typing/frame/coref is added.)
  - **Setting**: a role flag on already-typed `place` referents — which one names the scene's
    current physical setting. (feeds `09-location` / `10-topography`.)

  The artifact is one structured file per canto (JSON/JSONL with `## Scene s-e` checkpoints), the
  single source of truth for everything below.

**Checks on the artifact** (each independently code-verifiable; round-trip is *not* among them
because the corpus already guarantees spans):
1. **Coverage**: every corpus entity-candidate NP receives a typing decision; every entity mention
   has a referent; no referent is empty; every referent kind is in the closed type vocabulary; a
   set referent's members exist as referents in the scene; a pronoun referent does not echo its own
   surface (today's `_is_echo`, generalized).
2. **Relation validity**: every classified tuple cites an existing corpus skeleton tuple; predicate
   ∈ vocab; frame ∈ set; argument referent ids exist in the scene (today's `check_relations`,
   re-expressed over referents). A tuple whose subject and object resolve to the **same referent**
   is flagged at generation time (the `[1] meets [2]` both-Dante case KG-en.md deferred to Step 4):
   re-asked once, then accepted as flagged data if the model insists.
3. **Setting validity**: each setting flag points to a referent typed `place`.
4. **Partial-accept retry**: validated typings/referents/relations are kept; only failed items are
   re-asked in-conversation. The artifact is bigger than any single old output, so this is
   load-bearing — re-ask failed *referents/relations*, never regenerate the whole scene.

Use the **strongest reader** (ARCHITECTURE.md: coreference is reading-bound; small models regress
it). The interpretive budget is spent once, here, instead of 3–4×.

#### Preprocessing — noun census → frozen entity-type vocabulary

The entity-type vocabulary is established *before* Stage A prompting, by the same
measure-then-freeze method the predicate vocabulary already uses (`07-relations/measure.py`
computes `CLOSED_VOCAB`, human-curated and frozen before any prompt). A new `measure_entities.py`
(sibling to `measure.py`, sharing `dante_analyze` helpers) consumes the corpus **noun-phrase
enumeration** directly — no re-scanning of markup:

1. **Census**: aggregate the corpus's noun phrases across the whole poem; count head-noun
   frequencies (person, place, and everything else surface together because the corpus list is
   exhaustive).
2. **Propose a taxonomy**: cluster the census into candidate kinds; review the long tail to decide
   which kinds earn a closed label vs. folding into `non-entity`.
3. **Curate + freeze**: a human picks the closed entity-type vocabulary (person and place fully
   specified now; further kinds — object/artifact, creature, group, abstraction, work, time/event —
   only where the census justifies them) and freezes it in `dante_analyze/grammar.py` before Stage
   A runs. This is the closed list Stage A types against and the coverage check validates against.

This keeps typing empirical and transferable (the Premise: no external canon — the taxonomy comes
from the poem's own nouns), and bounds the current effort to person + place while leaving the
vocabulary open to grow from evidence.

The **predicate vocabulary gets the same treatment**: `CLOSED_VOCAB` was measured from the
*English readings'* `-s` verbs, but Stage A classifies *Italian lemmas* from the corpus skeleton —
an implicit cross-language mapping. Before freezing Stage A, re-run the measure over the corpus
Layer-5 predicate-lemma census and validate (or revise) `CLOSED_VOCAB` against it: same
measure-then-freeze method, better substrate.

### Stage B — consolidation (code-first)

All pure derivations of Stage A's referents and classified relations; reuse existing primitives.

- **Entities / registry** (replaces `05-registry` + typing): fold referent identities across all
  canticles via `fold_key`/`Nodes`, choose canonical spelling, apply the deterministic
  `aliases.txt`. **Type comes from A**, so `node_types.py`'s separate classification pass is gone —
  registry only *reconciles* the per-scene kinds onto one node. Reconciliation is explicit, not
  assumed: unanimous per-scene kinds → the node's type; a conflict → a flagged residual (LLM pick
  from the closed vocabulary over the node's scene evidence), with the disagreement rate reported
  as measurement. This deliberately reverses the documented node-level-typing decision (KG-en.md:
  "the type is a node property, not a tag property"): typing moves per-scene because it now binds
  to reading-anchored referents rather than bare labels, so the inconsistency node-level typing
  avoided becomes a measurable signal instead of a silent risk. Persons and places fold through the
  same machinery, partitioned by entity kind. Coreference is *already* resolved in A, so the
  `coref.txt` overlay disappears — its job moved into the checked artifact. Any residual cross-scene
  merge that is genuinely ambiguous becomes an explicit, flagged residual (LLM pick from a closed
  candidate set), not a silent human overlay.
- **Relation + speech graph** (replaces `06-speech` + `08-kg`): map each classified tuple's referent
  ids → canonical nodes; recover the asserter for `reported/prophecy/simile` from quote nesting
  (the corpus quote-span tree). Speaker attribution is direct **where a first-person referent
  exists**: A already resolved it (including pro-drop), so `06-speech`'s geometric first-person
  bucketing collapses to a lookup (`quotespans.own_region` + the resolved referent). Expect
  coverage to rise sharply — today 734 of 1,222 spans are `(unattributed)` because only explicit
  tags count, while A resolves pro-drop first persons too — but a span with no first-person
  mention at all still yields `(unattributed)`, kept as measured data, never force-resolved.
  Emit `nodes/edges/speech_edges.jsonl` as today.
- **Topography** (replaces `10-topography`): fold A's setting-flagged `place` referents into
  canonical regions (positional walk; LLM only on the same/new boundary, as today), with the *same*
  `fold_key`/`Nodes` machinery as persons.

### Stage C — context lock (code-first)

Because coreference and presence are decided in A, most of `11–13` becomes code:

- **Location** per scene: read directly from A's setting-flagged `place` referents (no separate LLM
  pass).
- **Presence**: frame-filtered — a referent that is an argument of a **`literal`-frame** relation
  (acts/speaks/is addressed), or a resolved speaker/addressee, is `present`; a referent appearing
  only inside `reported`/`prophecy`/`simile` frames is `mentioned` (Augusto in Virgilio's reported
  speech is not in the dark wood), and `hypothetical-simile`-typed referents are never `present` —
  derivable from A. LLM only on a true residual.
- **Addressee**: candidate pool = present cast − speaker, both already in A; resolve in code when
  ≤1, LLM pick when ≥2 (unchanged residual rule).
- **Cohort**: present cast filtered to `class/generic`; same residual rule.
- **Lock** (`14-lock`): unchanged pure-code join of the layers into per-scene TOML.

### Stage D — consumer

`15-digest` unchanged in spirit (bounded to the lock vocabulary; code conformance proof). It stays
a consumer, never a re-resolver.

---

## Shared-library changes

Follow the existing rule (ARCHITECTURE.md "put reused helpers in `dante_analyze/`"; no cross-pass
imports, no copies). Note that the morphology/NP/dependency/skeleton classifiers are **no longer
this repo's concern** — they are provided by the parse. What remains:

- **`dante_analyze/grammar.py` (new)**: the **frozen entity-type vocabulary** from the noun census
  (person sub-kinds + `place` + any census-justified kinds + `non-entity`/`deictic`), extending
  today's person-only `TYPES` in `dante_analyze/nodes.py`. Plus the interpretation-side helpers
  that survive (`_is_echo`/self-echo check, first-person resolution against the parse's pronoun
  forms). The surface classifiers that were duplicated across `labels.py`/`04-tags` —
  `is_capitalized_name`, `is_deictic`, `heads_name` — are dropped here; their answers come from the
  parse.
- **`dante_analyze/analysis.py` (new)**: the Stage-A artifact schema + loader
  (`load_analysis(canticle, canto) -> {(s,e): SceneAnalysis}`), plus the coverage / relation /
  setting checks (round-trip is the corpus's guarantee, not re-implemented here). Replaces the
  parse/check halves of `tags.py` and `relations.py`.
- **`dante_analyze/sceneproc.py` (new)**: the duplicated canto/scene loop (load parse →
  Turn-1 replay → Turn-2 ask → check → partial retry → checkpoint) shared today by
  `tags_canto`/`relations_canto`, as one driver parameterized by a worker, used by Stage A.
- **Reuse as-is**: `call_llm`, the `checkpoint.py` loaders/writers, `fold_key`/`norm_label`/
  `split_set`, `Nodes`, `quotespans.*`. Keep `measure.CLOSED_VOCAB` as the single predicate source.

---

## Invalidation model (resolve KG-PROBLEM.md)

With a single source of truth, granular invalidation becomes structural instead of a manual
`make clean`:

- The **unit** is the per-scene interpretation artifact. Each derived output records a content hash
  of the inputs it depends on (the scene artifact + the **corpus parse version** it annotated + the
  **`01-scenes` partition** that sliced it + the registry node-set it canonicalized against). A
  re-segmentation therefore invalidates exactly the affected scenes, like any other input change.
- On rerun, a derived unit recomputes iff its dependency hash changed. Stage B/C code passes
  recompute for free; the only cached LLM work (Stage A scenes, B/C residual picks, topography
  boundary, digest) is re-run **exactly** for the changed scenes — no more silent skipping, no more
  whole-pipeline clean. A bump in the corpus parse version invalidates exactly the scenes whose
  parse changed.
- A node-set change (e.g. a coreference fix in A) re-canonicalizes only the scenes whose referents
  touch the changed node, replacing the coarse fallback documented in `KG-PROBLEM.md`.

---

## Migration & validation strategy (measurement-gated, no big-bang cutover)

The current pipeline is committed and measured; the new one must prove equal-or-better before
replacing it. Build alongside, gate on metrics, then cut over.

0. **Noun census → freeze the entity-type vocabulary** (`measure_entities.py`, consuming the corpus
   NP enumeration). Propose and human-curate the closed kind list (person + place fleshed out;
   other kinds only where the census earns them), freeze it in `dante_analyze/grammar.py`. This must
   happen before any Stage A prompting, mirroring how `CLOSED_VOCAB` is frozen before
   `07-relations`. In the same step, re-measure `CLOSED_VOCAB` against the corpus Layer-5
   predicate-lemma census (see *Preprocessing*) and freeze the validated list.
1. **Spike Stage A on one canto** (e.g. Inferno I). Consume the parse; produce the artifact; confirm
   coverage/relation/setting checks pass and partial-retry works. Compare its referents/typings/
   relations against the existing `04-tags`/`07-relations` outputs for that canto.
2. **Derive Stage B from A** for that canto; diff `nodes/edges/speech_edges.jsonl` against the
   current `08-kg`. Treat the poem's known facts as the eval set (the Premise) — measure, do not
   hand-fix.
3. **Scale A+B to all 100 cantos**; report referent accuracy and edge agreement vs. the current
   graph. Decide go/no-go on the foundation here.
4. **Stage C** from A+B; rebuild the lock; **Stage D** digest. The end-to-end gate is the existing
   digest conformance metric (currently 99.5% within lock vocabulary) — the new pipeline must hold
   or beat it.
5. **Cut over**: renumber/retire `02–13` into the four-stage layout, update `Makefile`,
   `OVERVIEW.md`, `ARCHITECTURE.md`, `KG-PROBLEM.md` (close the invalidation item), and the per-pass
   READMEs. Keep the old passes in git history; do not delete until the new metrics are committed.

**ARCHITECTURE.md amendment.** The "keep model jobs narrow — one call, one job, one check" rule must
be restated: the *interpretive* job is now deliberately one larger call, and narrowness is enforced
by (a) the grammatical substrate being given (not re-derived here), (b) independent code checks per
interpretive facet, and (c) every non-interpretive layer being code-first. The same amendment
records the deliberate reversal of the node-level-typing decision (Stage B above) with its
rationale. Document this so the consolidation is not mistaken for a violation of the spine.

---

## Risks

- **Bigger artifact = bigger failure surface.** Mitigated by per-facet checks + strict
  partial-accept retry (re-ask failed referents/relations only). If retry stability regresses, fall
  back to splitting Turn 2 into two checked sub-turns (typing+coref, then relations) within the same
  conversation — still one reading.
- **Parse errors propagate.** The interpretation now trusts the corpus parse; a wrong NP boundary or
  role becomes a wrong entity or argument. Mitigated because the parse is itself checked and frozen
  upstream, and because Turn 1 (free reading) can still surface a contradiction the parse missed —
  but a parse regression is now a shared dependency to watch.
- **Coreference regression** if a weaker model is used to save cost. Keep the strongest reader for
  Stage A; measure before any downgrade (per ARCHITECTURE.md).
- **Unverifiable epithet merges** (the `coref.txt` human-review case) still have no structural
  check. Moving them into A makes the *decision* visible and checkable for coverage, but correctness
  of a periphrasis→name merge remains a measured residual, not a guarantee — call this out rather
  than implying it's solved.
- **Premise preservation**: Stage A must derive identities only from the text's own naming, no
  external canon. The checks must not smuggle in known geography/identities.

---

## Verification

- **Per-facet checks** on every Stage-A artifact: coverage (every NP typed; every mention
  referented; no pronoun self-echo), relation validity (cited skeleton id / predicate / frame /
  referent ids), setting validity. Run over all 100 cantos; zero check failures is the structural
  bar.
- **Graph agreement**: diff new `nodes/edges/speech_edges.jsonl` against the current `08-kg`; report
  adds/drops with the poem's known facts as the eval set.
- **Invalidation test**: change one referent in one scene; confirm only the dependent units
  recompute (hash-driven), and a full clean produces byte-identical output to the granular rerun.
- **End-to-end**: regenerate the lock and digest; the digest conformance metric must hold or beat
  the current 99.5%.
