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

There is no unfinished mandatory step in this repo. The knowledge graph and the translation context
lock are both complete; per-pass design and measured results live in each subdir's `README.md`, and
the context lock as a whole is described in `README.md` ("Context lock"). What remains below are
optional next directions, not a build queue — choose one before starting new work.

## Next directions

### 1. Digest edition — a proof of the context lock

Build an analyze-side prose digest from the resolved readings, **as the first consumer of the
context lock**. The point is not only the digest itself but a demonstration that `14-lock` is what
keeps a retelling from getting identities and settings wrong: the lock is the **primary input**, and
the digest exercises it. This is the natural payoff of the just-completed lock.

Goal: retell each canticle at story-reading density: more detailed than a plot summary, lighter than
a line-by-line translation.

Shape:

- one to two sentences per scene;
- scenes grouped into continuous paragraphs, roughly 3-5 paragraphs per canto;
- prose under `## Canto N` headings;
- separate from translation work, because it deliberately breaks line fidelity.

Primary inputs:

- `14-lock/<canticle>/NN.toml` via `load_lock(canticle, canto)` (exported from `dante_analyze`) — the
  per-scene identity-and-setting scaffold `{canticle, canto, scenes: [{lines, title, location,
  region, cohort, cast, speech, …}]}`, where `cast` is `[{who, status}]` and `speech` is
  `[{quote_id, lines, speaker, addressee, source}]`. This fixes names (source spelling), where we
  are, who is present versus merely mentioned, and who speaks to whom.
- `03-reading/<canticle>/NN.txt` for referent-resolved scene prose (what happens);
- `01-scenes/<canticle>/NN.json` for scene ranges and paragraph grouping;
- optionally `08-kg` via `load_kg` for who-does-what edges as an action anchor;
- source text through `dante-corpus` for anchoring.

How the lock is exercised: the digest draws every named figure and stated setting from the scene's
lock entry — it may not introduce an identity, location, region, cohort, speaker, or addressee that
the lock does not list for that scene. The lock is the closed vocabulary for *who* and *where*; the
reading supplies *what happens*. Identity resolution itself remains the KG's domain (`04-tags` →
`05-registry` → `08-kg`, with its gap parked in `KG-PROBLEM.md`); the digest consumes the resolved
result through the lock, it does not re-resolve.

Quality check — the proof:

- **lock conformance (the new, measurable check):** every proper name and setting the digest asserts
  for a scene must appear in that scene's lock entry (`cast` / `location` / `region` / `cohort` /
  `speech`). Staying inside the lock is the demonstration that it prevents identity-and-setting
  drift; deviations are the measurement, not something to hand-correct.
- narrative coherence and factual accuracy against the scene readings (`03-reading`), not line
  coverage.

Open design decisions (settle before coding):

- **output language** — English prose with source-spelling names (`Virgilio`), matching the rest of
  the analysis outputs? Confirm.
- **model** — strongest available reader; all calls through `dante_analyze.llm.call_llm`. This is
  uncheckable free prose, so CoT is permissible (ARCHITECTURE "Chain of thought policy").
- **layout & pass number** — per-canto files under a new `15-digest/`? Make a numbered pass only if
  it is committed as durable output (see note below).
- **KG use** — feed `08-kg` action edges as an event anchor, or rely on `03-reading` for events?
- **lock fields** — which lock fields the digest consumes. Note `14-lock` currently also carries
  `refer` / `relations` / `simile` / `basis`; a trim of those was discussed and deferred, so decide
  use-versus-ignore (and whether to revisit the trim) when settling this.

Implementation notes:

- Make a new numbered pass only if it is going to be committed as a durable output.
- Do not use a future translation as a dependency; a vetted translation could enrich the pass later.

### 2. Deferred quality work

These items are intentionally parked. They improve polish or storage, but they are not prerequisites
for the completed KG.

- Pronoun-layer marking quality: current local models still make clause-level and category errors on
  supplied pronouns.
- Remaining pronoun logic checks: misplaced supplied-pronoun detection and nominative-only supplied
  pronoun validation both need a reliable pronoun lexicon.
- Diff-only storage: store only additions relative to the source token list instead of full marked-up
  text.
- `05-registry` artifacts surfaced by `13-cohort/rollup.py`: a few registry entries bundle an
  individual with a collective and are typed `class` (e.g. `Dante, noble souls of Limbo`), so they
  flow through `11-presence` into cohort lines unchanged. Not a cohort defect — the fix belongs
  upstream in `05-registry` (re-measure, do not hand-correct the output). See `13-cohort/README.md`
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
