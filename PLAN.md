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

There is no unfinished mandatory step in this repo. The translation context lock (direction 1
below) is underway: its first five passes — **`09-location`** (per-scene local setting),
**`10-topography`** (the place analogue of `05-registry`), **`11-presence`** (present cast versus
merely-mentioned referents, the person analogue), **`12-addressee`** (who each speech span is
directed at), and **`13-cohort`** (which class of souls dwells in each scene) — are committed and
fully built across all 100 cantos; see their READMEs. The one remaining pass is `14-lock`.

## Next directions

### 1. Translation context lock (active direction)

Build a per-scene **context lock**: an identity-and-setting record that fixes what a translation or
digest must not get wrong — who speaks and is addressed, who/what each referring expression
resolves to, where the scene is set, who is present versus merely mentioned. Identity and setting
**only**: never the source's meaning or a paraphrase. Each entry carries a `basis` source quote so
it is verifiable. The parked spec sketch is `ref/PLAN.md`, with `ref/inferno-01.toml` as a
hand-written sample — treat it as illustration, **not** the confirmed spec.

This direction comes before the digest (2): it is the natural payoff of the just-completed KG, it
consumes the freshest work (`05-08`), it has a concrete evaluation target, and a vetted lock then
gives the digest a clean, consistent identity base to build on.

**The KG is action-only.** `08-kg` represents who-does-what edges; it carries no setting
(location / region / cohort), because those are narrative *state*, not actions. Supplying that
missing layer is the lock's substantive new work.

**Derive everything from the text.** Per the repository premise (README "Premise"), no external
canon is an input. The poem's known geography is an *evaluation* target, not a lookup table. So the
setting layer is built bottom-up from the source, mirroring the person pipeline already in place
(`04-tags` surface → `05-registry` canonical), applied to places.

The work splits into kinds, kept separate — **one judgment per script**, so judgments never
contaminate each other:

- **code join (no LLM)** from KG / `04-tags` / `05-registry`: `speaker` (speech edges), referent
  resolution (who/what → canonical), `relations` (edges), `simile` (frame=simile edges);
- **single text-derived LLM judgments**, each its own pass: presence (cast versus merely
  mentioned) — committed as `11-presence`; addressee (who each speech span is directed at) —
  committed as `12-addressee` (see their READMEs);
- **setting**: location and its consolidation into canonical regions — committed as `09-location`
  and `10-topography` (see their READMEs). Cohort (which class of souls dwells in each scene) is a
  distinct judgment — committed as `13-cohort`, with `rollup.py` folding the per-scene cohorts onto
  the canonical regions by code.

Distinctions the lock must preserve:

- **present cast** versus **merely-mentioned referents**.

With `09-location`, `10-topography`, `11-presence`, `12-addressee`, and `13-cohort` committed (see
their READMEs), the one remaining pass (continuing the `NN-name` ladder) is:

- `14-lock` (pure code) — join all of the above plus the KG into the per-canto lock, with a
  structural check, exactly as `08-kg` joins.

`13-cohort` settled the cohort layer with the same code-first, closed-set, LLM-residual pattern as
`11` / `12`, judged **per scene** (not per region, which `measure.py` showed balloons the candidate
set and conflates merged terraces); `rollup.py` builds the per-region view by code afterward.

**Starting `14-lock` (a fresh session can begin here).** It is the last pass and pure code (no
model), so the work is design then join — start by writing `14-lock/PLAN.md` per the pass-doc
convention. Before coding, settle the two open design points below (output format, exact lock field
set); they are deliberately deferred to this pass, not yet decided.

- *Decide first:* output format (per-canto TOML vs JSONL — see Open decisions) and the lock's field
  set. `ref/PLAN.md` + `ref/inferno-01.toml` are the spec **sketch** (illustration, not confirmed);
  treat them as a starting proposal to confirm, not a fixed schema.
- *Inputs to join (all committed):* `08-kg` (nodes / edges / speech_edges), plus the five context-lock
  layers via their `dante_analyze.checkpoint` loaders — `load_locations`, `load_topography`,
  `load_presence`, `load_addressee`, `load_cohort` (all exported from `dante_analyze`, beside one
  another). Each layer's README documents its loader's return shape.
- *Pattern to follow:* `08-kg` (`08-kg/README.md`) — the existing pure-code join that resolves cited
  `[n]` tags through `load_tags` → `load_registry` and emits per-canticle output with a geometry
  check. `14-lock` is the same shape over the lock layers, per canto.
- *Check + evaluation:* a structural check (every scene gets a lock entry; basis ranges in-scene),
  then compare a generated Inferno 1 lock against `ref/inferno-01.toml` **structurally**, not
  string-exact (name-form differs).

Open decisions:

- output format (per-canto TOML versus JSONL) — settle at the lock pass (`14-lock`);
- name form: source spelling (`Virgilio`), matching the KG nodes; anglicization belongs to
  `dante-dravidian`'s glossary, not here;
- deferred, outside identity-only scope: dramatic-irony flags (`misnames-addressee`) and explanatory
  `note` prose;
- evaluation: compare a generated Inferno 1 lock against `ref/inferno-01.toml` **structurally**, not
  string-exact (given the name-form difference).

### 2. Digest edition

Build an analyze-side prose digest from the resolved readings. Natural to do after the context lock
(1), whose resolved identities and settings it can reuse for consistent naming.

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

### 3. Deferred quality work

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
