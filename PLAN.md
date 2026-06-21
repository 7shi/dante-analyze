# dante-analyze plan

Status: the analysis pipeline is complete through the knowledge graph and the translation context
lock. The remaining work is not a build queue; it is a short list of possible next directions.
Choose one before starting new work.

For current usage, layout, and completed-pass summaries, see `README.md`. For local-LLM engineering
rules, read `ARCHITECTURE.md` before changing an existing pass or creating a new one.

## Current state

The committed pipeline covers all three canticles, 100 cantos:

1. `01-scenes` segments the poem into scenes.
2. `02-markup -> 03-reading -> 04-tags` resolves references at scene level.
3. `05-registry -> 06-speech -> 07-relations -> 08-kg` turns the resolved material into a
   per-canticle knowledge graph.
4. `09-location -> 10-topography -> 11-presence -> 12-addressee -> 13-cohort -> 14-lock` builds the
   per-scene translation context lock on top of the graph.

There is no unfinished mandatory step in this repo. The knowledge graph, the translation context
lock, and the digest edition that consumes it are all complete; per-pass design and measured results
live in each subdir's `README.md`, and the context lock and digest are described in `README.md`
("Context lock", "Digest edition"). What remains below are optional next directions, not a build
queue — choose one before starting new work.

## Next directions

### 1. Digest follow-ups

The digest edition itself is complete (`15-digest/`, all three canticles; design and measured proof
in `15-digest/README.md` and the README "Digest edition"). These optional refinements are not started:

- tune the `digest show` paragraph grouping;
- consider generating Japanese independently from the reading rather than translating from the English;
- refine `conformance.py` to whitelist liturgical quotes / reverent pronouns — method polish that
  would not change the proof.

### 2. Deferred quality work

These items are intentionally parked. They improve polish or storage, but they are not prerequisites
for the completed KG.

- Pronoun-layer marking quality: current local models still make clause-level and category errors on
  supplied pronouns.
- Remaining pronoun logic checks: misplaced supplied-pronoun detection and nominative-only supplied
  pronoun validation both need a reliable pronoun lexicon.
- Diff-only storage: store only additions relative to the source token list instead of full marked-up
  text.
- ~~`class`-typed individual+collective bundles~~ (RESOLVED): `Dante, noble souls of Limbo`-style
  bundles are now split at node construction — `Nodes._gather` promotes the lowercase collective
  remainder to its own node so the label resolves as a `set` (the individual rejoins its own node,
  the collective becomes its own `class` node). See `ARCHITECTURE.md` and `13-cohort/README.md`
  "Notes".

## Rules to keep

- Use source-spelling names in analysis outputs: `Virgilio`, not `Virgil`.
- Keep identity-first labels: commit the most specific identification the reading establishes, not a
  scene-local epithet for a figure already identified.
- Do not leak answers into prompts. Prompts may include source text and general knowledge, never
  per-item answers or worked examples from the item being processed.
- Derive every assertion from the source text; never feed external canon (known geography,
  identities, glossed periphrases) into a pass. The poem's known facts are an evaluation set, not an
  input — see the README "Premise". This is what keeps the method transferable to obscure works.
- Put all ordinary LLM calls through `dante_analyze.llm.call_llm`. `01-scenes` is the exception
  because it uses `llm7shi` structured output directly.
- Normalize mechanical orthography in code, not in prompts.
- Move shared helpers into `dante_analyze/`; do not import across numbered passes or copy helpers.
- Preserve the reading/tags split: `03-reading` is free interpretation, `04-tags` is tag-anchored
  formalization.
- Treat the pipeline as an experiment in local-LLM capability. Do not hand-proofread generated
  outputs to make the committed data look better; improve the method and re-measure instead.

## Pass documentation convention

While a pass is being designed, keep a `PLAN.md` inside that pass directory. When the pass is
complete, rewrite that file into `README.md` rather than renaming it mechanically.

The completed `README.md` should explain:

- what the pass is for;
- what it reads and writes;
- what checks it performs;
- how to run it;
- measured results from the committed output where relevant.

Drop build-time scaffolding such as remaining-work lists and step-by-step construction notes once the
pass is complete.
