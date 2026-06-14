# dante-analyze plan

Status: the analysis pipeline is complete through the knowledge graph. The remaining work is not a
build queue; it is a short list of possible next directions. Choose one before starting new work.

For current usage, layout, and completed-pass summaries, see `README.md`. For local-LLM engineering
rules, read `ARCHITECTURE.md` before changing an existing pass or creating a new one.

## Current state

The committed pipeline covers all three canticles, 100 cantos:

1. `01-scenes` segments the poem into scenes.
2. `02-markup -> 03-reading -> 04-tags` resolves references at scene level.
3. `05-registry -> 06-speech -> 07-relations -> 08-kg` turns the resolved material into a
   per-canticle knowledge graph.

There is no unfinished mandatory step in this repo.

## Next directions

### 1. Digest edition

Build an analyze-side prose digest from the resolved readings. This is the most natural next
deliverable inside this repo.

Goal: retell each canticle at story-reading density: more detailed than a plot summary, lighter than
a line-by-line translation.

Shape:

- one to two sentences per scene;
- scenes grouped into continuous paragraphs, roughly 3-5 paragraphs per canto;
- prose under `## Canto N` headings;
- separate from translation work, because it deliberately breaks line fidelity.

Primary inputs:

- `03-reading/<canticle>/NN.txt` for referent-resolved scene prose;
- `01-scenes/<canticle>/NN.json` for scene ranges and grouping;
- source text through `dante-corpus` for anchoring.

Implementation notes:

- Make a new numbered pass only if it is going to be committed as a durable output.
- Its quality check should be narrative coherence and factual accuracy against the scene readings,
  not line coverage.
- Do not use a future translation as a dependency; a vetted translation could enrich the pass later.

### 2. Translation context lock

Turn the graph's speaker and relation data into the identity lock needed by `dante-dravidian`.

This is downstream-facing, but the ownership belongs here because it is referent resolution rather
than translation. The parked detailed spec is in `ref/PLAN.md`, with `ref/inferno-01.toml` as the
hand-written reference sample.

Likely starting point:

- derive `speaker`, `addressee`, and `cast` from `04-tags`, `06-speech`, and `08-kg`;
- derive identity-bearing relations from `07-relations` / `08-kg`;
- keep the lock identity-only: no paraphrase, no translation decisions;
- use source-spelling names unless a single explicit normalization point is added.

Open design work:

- decide whether the lock is generated directly from graph JSONL or through a new pass-specific
  intermediate;
- define the TOML writer and checker;
- compare a generated Inferno 1 lock against `ref/inferno-01.toml`.

### 3. Deferred quality work

These items are intentionally parked. They improve polish or storage, but they are not prerequisites
for the completed KG.

- Pronoun-layer marking quality: current local models still make clause-level and category errors on
  supplied pronouns.
- Remaining pronoun logic checks: misplaced supplied-pronoun detection and nominative-only supplied
  pronoun validation both need a reliable pronoun lexicon.
- Diff-only storage: store only additions relative to the source token list instead of full marked-up
  text.

## Rules to keep

- Use source-spelling names in analysis outputs: `Virgilio`, not `Virgil`.
- Keep identity-first labels: commit the most specific identification the reading establishes, not a
  scene-local epithet for a figure already identified.
- Do not leak answers into prompts. Prompts may include source text and general knowledge, never
  per-item answers or worked examples from the item being processed.
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
