# Re-architecture: a single grammatical-analysis foundation for entities & relations

## Context

The 15-pass pipeline (`OVERVIEW.md`) works end-to-end: source text → referent-resolved
knowledge graph → per-scene translation lock → bilingual digest. It was built as a "make
something that runs" stack, and it shows: the same scene is LLM-analyzed 3–4 times, and the
grammatical knowledge needed to do that is scattered ad hoc across passes ("屋上屋を重ねた").

What the pipeline does is, in principle, two things: **extract entities** and **extract
relations**. Pronoun / pro-drop / epithet resolution (coreference) is *preparation* for both.
The current design instead spreads that preparation, and the extraction itself, across many
passes that each re-read and re-analyze the text. Concrete evidence found in the codebase:

- **Text re-read 3–4×.** `02-markup` (mark) → `03-reading` (interpret) → `04-tags` (formalize
  WHO) → `07-relations` (edges) each call the model on the same scene. `number_scene()` runs
  ~4× per scene; `build_reason_prompt()` (Turn 1, identical text) is regenerated 3× per scene.
- **Duplicated control flow.** `04-tags/tags.py::tags_canto` and
  `07-relations/relations.py::relations_canto` are near character-identical (same load →
  `number_scene` → Turn-1 reading replay → Turn-2 ask → parse → check → retry loop), differing
  only in `OUT_DIR` and the per-scene worker.
- **Scattered grammar classification.** `is_capitalized_name`, `is_deictic`, `heads_name`,
  `_is_echo`, plus the `FIRST_PERSON_*` sets, answer overlapping questions about
  name/epithet/pronoun/deictic across `dante_analyze/labels.py`, `04-tags/tags.py`,
  `04-tags/coreference.py`.
- **Coreference is a late patch.** Identity is resolved per-scene (03/04), folded globally
  (05), then *re-resolved* by the human-reviewed `04-tags/coref.txt` overlay applied at the
  `load_tags` layer — an unverifiable merge bolted on after the fact.
- **Repeated roster work + no granular invalidation.** `11→12→13` each re-gather and
  re-canonicalize the scene roster; and per `KG-PROBLEM.md` a node-set change does not
  propagate granularly — the cached LLM passes silently skip changed scenes, so the only safe
  rebuild is a full `make clean && make`.

**Intended outcome.** Replace the ladder's redundant re-reading with **one comprehensive,
checkable grammatical analysis per scene** that resolves coreference up front, and make every
downstream layer (entities, relations, speech, presence/addressee/cohort, location, lock,
digest) a **code-first derivation** of that single source of truth, with the model called only
on a genuine residual. Scope confirmed with the user: **whole pipeline (01–15)**; foundation =
**single structured analysis as source of truth**; **coreference internalized** in it.

This plan is design-only. No implementation here.

---

## Target architecture

Four stages instead of fifteen ad hoc passes. The spine is unchanged in spirit — *the model
proposes; code checks, normalizes, joins, resumes* — but the model's single proposal is now a
rich grammatical analysis, and the narrowness moves into the derivations being code.

```
corpus ──> [A] Grammatical analysis (per scene, LLM)  ── the only interpretive pass
                  │  reading (deliberation) → structured analysis (checked)
                  │  mentions + typed referents (coref) + predicate-argument clauses + setting
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

### Stage A — the grammatical-analysis foundation (the one interpretive pass)

A single LLM conversation per scene, replacing `02-markup` + `03-reading` + `04-tags` +
`07-relations` (and absorbing the `coref.txt` overlay). Two turns, reusing the existing
"split deliberation from final output" rule:

- **Turn 1 — reading (deliberation).** Free prose "who does what, who speaks to whom",
  CoT on. This is today's `03-reading`, kept verbatim as the reasoning anchor and replayed as
  the assistant turn. Uncheckable by design; errors accepted as data (the Premise).
- **Turn 2 — structured analysis (checked).** One artifact per scene capturing:
  - **Mentions**: every entity reference — *person and place alike* — with its source span and
    surface, classified by **form** `name | epithet | pronoun | supplied-subject(pro-drop)`.
    (subsumes `02-markup`)
  - **Typed referents (one extraction across entity kinds)**: each mention links to a
    scene-local *referent id*; each referent carries an **entity kind** and its most-specific
    identity in source spelling, or `(unknown)`. The kind comes from a single closed
    **entity-type vocabulary** that is *not* hardcoded to person/place but **derived from a
    noun census** (see below) — person and place are the two richly-developed, highest-priority
    kinds (the current effort), with further kinds (e.g. object/artifact, creature/beast,
    group/collective, abstraction/personification, work/text, time/event) defined only as the
    census shows they earn their place. The person branch keeps today's sub-kinds
    `{individual, generic, class, hypothetical-simile}`; `deictic` and `non-entity` remain as
    cross-cutting markers. Typing once, here, alongside extraction is the efficiency win the
    user asked for: every noun-headed entity is pulled in the same pass instead of a person
    ladder plus a separate `09-location` place extraction. Pronouns/pro-drop/epithets resolve
    *here*, up front. (subsumes `04-tags` + `coref.txt` + the typing step + `09-location`'s
    extraction)
  - **Clauses**: predicate-argument tuples `(subj-referent, predicate, obj-referent)` with a
    `frame ∈ {literal, simile, prophecy, reported}` and a source line range, citing referent
    ids — not raw text. (subsumes `07-relations`)
  - **Setting**: which `place`-kind referent(s) name the scene's current physical setting —
    a *role flag on already-typed place referents*, not a separate place extraction. (feeds
    `09-location`/`10-topography`)

  Predicates stay the closed `measure.CLOSED_VOCAB ∪ {relates-to}`. The artifact is one
  structured file per canto (JSON/JSONL with `## Scene s-e` checkpoints), the single source of
  truth for everything below.

**Checks on the artifact** (each independently code-verifiable, preserving measurability):
1. **Round-trip**: every mention span reproduces the source substring verbatim (today's
   `strip_to_source` round-trip, applied per mention).
2. **Coverage**: every marked mention has a referent; no referent is empty; every referent's
   entity kind is in the closed type vocabulary; a pronoun referent does not echo its own
   surface (today's `_is_echo` check, generalized).
3. **Clause validity**: cited referent ids exist in the scene; predicate ∈ vocab; frame ∈ set;
   line range within scene (today's `check_relations`).
4. **Partial-accept retry**: validated mentions/clauses are kept; only failed items are
   re-asked in-conversation (the existing accumulate-good-results discipline). The artifact is
   bigger than any single old output, so this is load-bearing — it must re-ask failed
   *referents/clauses*, never regenerate the whole scene.

Use the **strongest reader** (ARCHITECTURE.md: coreference is reading-bound; small models
regress it). The interpretive budget is spent once, here, instead of 3–4×.

#### Preprocessing — noun census → frozen entity-type vocabulary

The entity-type vocabulary is established *before* Stage A prompting, by the same
measure-then-freeze method the predicate vocabulary already uses (`07-relations/measure.py`
computes `CLOSED_VOCAB` from the readings, human-curated and frozen before any prompt). A new
`measure_entities.py` (sibling to `measure.py`, sharing `dante_analyze` helpers):

1. **Census**: enumerate every noun / noun-headed surface across the corpus (the markup's
   `{..}` person-noun marks are a starting signal; widen to all common/proper nouns so
   non-person, non-place entities surface too). Count frequencies.
2. **Propose a taxonomy**: cluster the census into candidate kinds; review the long tail to
   decide which kinds are worth a closed label vs. folding into `non-entity`.
3. **Curate + freeze**: a human picks the closed entity-type vocabulary (person and place
   fully specified now; other kinds added only where the census justifies them) and freezes it
   before Stage A runs — exactly the predicate-vocab discipline. The frozen set lives in
   `dante_analyze/grammar.py` and is the closed list Stage A types against and the coverage
   check validates against.

This keeps typing empirical and transferable (the Premise: no external canon — the taxonomy
comes from the poem's own nouns, not an imported ontology), and bounds the current effort to
person + place while leaving the vocabulary open to grow from evidence.

### Stage B — consolidation (code-first)

All pure derivations of Stage A's referents and clauses; reuse existing primitives.

- **Entities / registry** (replaces `05-registry` + typing): fold referent identities across
  all canticles via `fold_key`/`Nodes`, choose canonical spelling, apply the deterministic
  `aliases.txt`. **Type comes from A**, so `node_types.py`'s separate classification pass is
  gone — registry only *reconciles* the per-scene kinds onto one node (resolving the rare
  per-scene disagreement, the same dedup win `05-registry/README.md` cites). Persons and places
  fold through the same machinery, partitioned by entity kind. Coreference is *already* resolved
  in A, so the `coref.txt` overlay disappears too — its job moved into the checked artifact. Any
  residual cross-scene merge that is genuinely ambiguous becomes an explicit, flagged residual
  (LLM pick from a closed candidate set), not a silent human overlay.
- **Relation + speech graph** (replaces `06-speech` + `08-kg`): map each clause's referent ids
  → canonical nodes; recover the asserter for `reported/prophecy/simile` from quote nesting.
  Speaker attribution is now direct: A already resolved the first-person referent, so
  `06-speech`'s geometric first-person bucketing collapses to a lookup
  (`quotespans.own_region` + the resolved referent). Emit `nodes/edges/speech_edges.jsonl` as
  today.
- **Topography** (replaces `10-topography`): fold A's `place`-kind referents flagged as setting
  into canonical regions (positional walk; LLM only on the same/new boundary, as today). Because
  place is now a first-class entity kind in A, this folds places with the *same* `fold_key`/
  `Nodes` machinery as persons, instead of a parallel place-only extraction.

### Stage C — context lock (code-first)

Because coreference and presence are now decided in A's mentions/clauses, most of `11–13`
becomes code:

- **Location** per scene: read directly from A's setting-flagged `place` referents (no separate
  LLM pass).
- **Presence**: a mention that is a clause argument (acts/speaks/is addressed) is `present`;
  a mention only named is `mentioned` — derivable from A. LLM only on a true residual.
- **Addressee**: candidate pool = present cast − speaker, both already in A; resolve in code
  when ≤1, LLM pick when ≥2 (unchanged residual rule, but the roster is gathered once).
- **Cohort**: present cast filtered to `class/generic`; same residual rule.
- **Lock** (`14-lock`): unchanged pure-code join of the layers into per-scene TOML.

### Stage D — consumer

`15-digest` unchanged in spirit (bounded to the lock vocabulary; code conformance proof). It
stays a consumer, never a re-resolver.

---

## Shared-library changes

Follow the existing rule (ARCHITECTURE.md "put reused helpers in `dante_analyze/`"; no
cross-pass imports, no copies). Concretely:

- **`dante_analyze/grammar.py` (new)**: one place for all mention/label classification —
  consolidate `is_capitalized_name`, `is_deictic`, `heads_name`, `_is_echo`, and the
  `FIRST_PERSON_*` sets into a single classifier that computes all properties of a surface at
  once. Also home the **frozen entity-type vocabulary** produced by the noun census (person
  sub-kinds + `place` + any census-justified kinds + `non-entity`/`deictic`), extending today's
  person-only `TYPES` in `dante_analyze/nodes.py`. Stage A and Stage B both use it. The census
  itself is a one-off measurement script (`measure_entities.py`, sibling to
  `07-relations/measure.py`), not a runtime dependency.
- **`dante_analyze/analysis.py` (new)**: the Stage-A artifact schema + loader
  (`load_analysis(canticle, canto) -> {(s,e): SceneAnalysis}`), plus per-mention round-trip /
  coverage / clause checks. This replaces the parse/check halves of `tags.py` and
  `relations.py`.
- **`dante_analyze/sceneproc.py` (new)**: extract the duplicated canto/scene loop
  (load → `number_scene` → Turn-1 replay → Turn-2 ask → parse → check → partial retry →
  checkpoint) shared today by `tags_canto`/`relations_canto` into one driver parameterized by
  a worker, used by Stage A.
- **Reuse as-is**: `call_llm`, the `checkpoint.py` loaders/writers, `marks.py`
  (`number_scene`, `tag_positions`, `strip_to_source`), `fold_key`/`norm_label`/`split_set`,
  `Nodes`, `quotespans.*`. Keep `measure.CLOSED_VOCAB` as the single predicate source.

---

## Invalidation model (resolve KG-PROBLEM.md)

With a single source of truth, granular invalidation becomes structural instead of a manual
`make clean`:

- The **unit** is the per-scene analysis artifact. Each derived output records a content hash
  of the inputs it depends on (the scene artifact + the registry node-set it canonicalized
  against).
- On rerun, a derived unit recomputes iff its dependency hash changed. Stage B/C code passes
  recompute for free; the only cached LLM work (Stage A scenes, B/C residual picks, topography
  boundary, digest) is re-run **exactly** for the changed scenes — no more silent skipping,
  no more whole-pipeline clean.
- A node-set change (e.g. a coreference fix in A) re-canonicalizes only the scenes whose
  referents touch the changed node, via the hash, replacing the coarse fallback documented in
  `KG-PROBLEM.md`.

---

## Migration & validation strategy (measurement-gated, no big-bang cutover)

The current pipeline is committed and measured; the new one must prove equal-or-better before
replacing it. Build alongside, gate on metrics, then cut over.

0. **Noun census → freeze the entity-type vocabulary** (`measure_entities.py`). Enumerate the
   corpus's nouns, propose and human-curate the closed kind list (person + place fleshed out;
   other kinds only where the census earns them), freeze it in `dante_analyze/grammar.py`. This
   must happen before any Stage A prompting, mirroring how `CLOSED_VOCAB` is frozen before
   `07-relations`.
1. **Spike Stage A on one canto** (e.g. Inferno I). Produce the artifact; confirm all four
   checks pass and partial-retry works. Compare its mentions/referents/clauses against the
   existing `04-tags`/`07-relations` outputs for that canto.
2. **Derive Stage B from A** for that canto; diff `nodes/edges/speech_edges.jsonl` against the
   current `08-kg`. Treat the poem's known facts as the eval set (the Premise) — measure, do
   not hand-fix.
3. **Scale A+B to all 100 cantos**; report referent accuracy and edge agreement vs. the
   current graph. Decide go/no-go on the foundation here.
4. **Stage C** from A+B; rebuild the lock; **Stage D** digest. The end-to-end gate is the
   existing digest conformance metric (currently 99.5% within lock vocabulary) — the new
   pipeline must hold or beat it.
5. **Cut over**: renumber/retire `02–13` into the four-stage layout, update `Makefile`s,
   `OVERVIEW.md`, `ARCHITECTURE.md`, `KG-PROBLEM.md` (close the invalidation item), and the
   per-pass READMEs. Keep the old passes in git history; do not delete until the new metrics
   are committed.

**ARCHITECTURE.md amendment.** The "keep model jobs narrow — one call, one job, one check"
rule must be restated: the *interpretive* job (grammatical analysis) is now deliberately one
larger call, and narrowness is enforced by (a) independent code checks per output facet and
(b) every non-interpretive layer being code-first. Document this so the consolidation is not
mistaken for a violation of the spine.

---

## Risks

- **Bigger artifact = bigger failure surface.** Mitigated by per-facet checks + strict
  partial-accept retry (re-ask failed referents/clauses only). If retry stability regresses,
  fall back to splitting Turn 2 into two checked sub-turns (mentions+coref, then clauses)
  within the same conversation — still one reading, no extra re-read.
- **Coreference regression** if a weaker model is used to save cost. Keep the strongest reader
  for Stage A; measure before any downgrade (per ARCHITECTURE.md).
- **Unverifiable epithet merges** (the `coref.txt` human-review case) still have no structural
  check. Moving them into A makes the *decision* visible and checkable for coverage, but
  correctness of a periphrasis→name merge remains a measured residual, not a guarantee — call
  this out rather than implying it's solved.
- **Premise preservation**: Stage A must derive identities only from the text's own naming, no
  external canon. The checks must not smuggle in known geography/identities.

---

## Verification

- **Per-facet checks** on every Stage-A artifact: round-trip (mention spans = source),
  coverage (every mention referented; no pronoun self-echo), clause validity (ids/predicate/
  frame/lines). Run over all 100 cantos; zero check failures is the structural bar.
- **Graph agreement**: diff new `nodes/edges/speech_edges.jsonl` against the current `08-kg`;
  report adds/drops with the poem's known facts as the eval set.
- **Invalidation test**: change one referent in one scene; confirm only the dependent units
  recompute (hash-driven), and a full clean produces byte-identical output to the granular
  rerun.
- **End-to-end**: regenerate the lock and digest; the digest conformance metric must hold or
  beat the current 99.5%.
