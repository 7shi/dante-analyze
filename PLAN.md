# dante-analyze — analysis layer: plan & status (2026-06)

> **▶ STATUS: pipeline = scenes → markup → reading → tags ✓; next = registry (Active work 1)**
>
> 1. ✓ **`02-markup/markup.py`** — single pass, `gemma4:31b-it-qat` + CoT on; markup
>    regenerated for all canticles and committed.
> 2. ✓ **`03-reading/reading.py`** — readings regenerated on the new markup and committed.
> 3. ✓ **`04-tags/`** — the identity-first per-tag resolution pass (design: `04-tags/PLAN.md`).
>    Implemented; full run complete (100 files, all three canticles), committed.
> 4. **Downstream layer** (registry → speech edges → relations → KG assembly) — design from
>    measured outputs; see Active work 1–4.

### Sanity check (run before committing)

```bash
cd /home/7shi/repos/dante-analyze
uv run python -c "import dante_analyze; print('ok')"
uv run dante-analyze tags show inferno 1
```

`dante-analyze` turns the source cantos into referent-resolved structured data (the
precursor to a knowledge graph). It consumes the shared corpus — source lines, tokens,
scene ranges, and the quote-span tree — from **`dante-corpus`** via its Python API, and
runs the LLM analysis passes on top. Every pass drives a **local LLM**; the patterns they
share are written up once in **`ARCHITECTURE.md`** — read that before building or changing
a pass here.

The pass scripts (`02-markup/markup.py`, `03-reading/reading.py`, `04-tags/tags.py`)
live in their pipeline subdirectory and import the
shared library package `dante_analyze/`. All LLM calls go
through the single shared gateway `call_llm` (from `dante_analyze/llm.py`).

## Active work

1. **Registry / entity reconciliation (the node table)** [next; mostly code].
   Aggregate the per-scene `04-tags/` labels across each canticle into one canonical,
   source-spelled node per figure, grouping by the identity the reading states. Required: a **node-type classification**
   (individual / generic / class / hypothetical-simile / non-person), support for a tag
   resolving to a **set** of figures (`Cammilla, Eurialo, Turno, Niso`), and **aliases with
   provenance** — the alias surfaces come from the markup itself (`number_scene`'s meta
   carries each tag's surface form), code-extracted, paired with tags' identities. Mostly
   code over a bounded cast; a small model step only for residual groupings a join can't
   settle. **Measure before speccing**: how often identity is already pinned, how many
   epithet-only figures remain.

2. **Speech edges by deterministic join** [with 1; pure code].
   Quote spans (dante-corpus) × `04-tags/` referents: a span's internal first-person tag's
   referent is the speaker, child spans excluded so reported speech separates cleanly.
   Measure coverage (what fraction of quotes carry an internal first-person tag) before
   deciding whether residuals need a model.

3. **Relations pass** [design after 1–2 are measured].
   The event-edge input the KG still lacks: one LLM pass per scene, bound directly to the
   reading like tags.py, emitting line-oriented relations with **role-explicit tag
   citations** (subject before predicate, object after), a **closed predicate vocabulary**,
   a **frame marker** (literal / simile / prophecy / reported), and the covered line range —
   all four structurally checkable. Example line format:
   `- [3] guides [4] | frame: literal | lines 112-114`
   or `- [1] says-that [2] defeats [11] | frame: prophecy | lines 100-105`.

4. **KG assembly** [last; pure code].
   Join relations' tag citations through `04-tags/` to the registry's canonical nodes;
   attach provenance (canticle/canto/scene/lines + tag numbers) and frame to every edge;
   merge the speech edges. The checks of the upstream passes are what make this join total.

## Pipeline (data flow)

```
  dante-corpus (shared inputs, via the dante_corpus API — no LLM):
     source cantos ─→ canto.lines() / Line.tokens     normalized lines + tokens   [done]
                   ─→ canto.quotes()                   quote-span tree             [done]

  dante-analyze (this repo — scene data + local-LLM passes):
     01-scenes/<c>/NN.json ─→ load_scenes()              scene line-ranges          [done]
     02-markup/markup.py   ─→ 02-markup/<c>/NN.txt       pronoun + name marks       [done]
                        (single pass, gemma4:31b-it-qat + CoT on, token-boundary normalization)
     03-reading/reading.py ─→ 03-reading/<c>/NN.txt      free prose reading         [done]
                                                     (committed, not proofread, no check)
     04-tags/tags.py       ─→ 04-tags/<c>/NN.txt         n. Name identity-first     [done]
                                                     resolution (checked, reader)
     (downstream) ─→ TBD                           registry (nodes) + speech    [next: design
                                                   edges + relations + assembly  from outputs]
        ↑ Active work 1–4. The speaker/edge data is intended to feed the
          translation context lock (dante-dravidian).
```

## Scripts — purpose & status

Scene segmentation (`01-scenes/<canticle>/NN.json`) is owned by this repo. The tokenizer and
quote-span tree are provided by **dante-corpus** and consumed through its API.

- **`02-markup/markup.py`** [done] — per-scene reference markup; single pass, `gemma4:31b-it-qat` + CoT on, both pronoun and name layers; `normalize_token_brackets` post-LLM (ARCH §12); round-trip checked.
- **`dante_analyze/`** [done] — shared library: `corpus.py`, `checkpoint.py`, `marks.py` (`number_scene`, `unbrace`, `fix_elision`), `llm.py` (`call_llm`), `prompts.py` (`build_reason_prompt`), `cli.py`; all re-exported from `__init__.py`.
- **`03-reading/reading.py`** [done] — free prose reading per scene, CoT on, `gemma4:31b-it-qat`; no check, not proofread; single source of truth for WHO (ARCH §11).
- **`04-tags/tags.py`** [done] — identity-first `n. Name` resolution per scene; replays reading as reasoning turn; `fix_elision` in code (ARCH §12); structure-checked (ARCH §11); design: `04-tags/PLAN.md`.
- **`dante_analyze/cli.py`** [done] — read-only query CLI: `dante-analyze {scenes,reading,tags} show <canticle> <canto>`.

## Deferred

- **Pronoun-layer marking quality** — local models still make errors on Inferno 1:
  spurious/misplaced `[+pron]` supply (needs clause parsing), non-pronoun bracketed,
  wrong pronoun category/form. The hard classes need a stronger model; the partly-
  checkable classes are deferred pending a reliable pronoun lexicon.
- **Remaining pronoun-layer logic checks** — misplaced-supply detection (`[+..]` not
  immediately before a verb); nominative-only supplied-pronoun check. Both need a
  pronoun lexicon.
- **Diff-only storage** — store only additions vs. the source token list.

## Decisions to keep

- **Source-spelling names** everywhere (`Virgilio`, not "Virgil"), **identity-first**: the
  committed label is the most specific identification the reading establishes, never a
  scene-local epithet for a figure the reading already names (ARCH §11).
- **No answer leakage**: prompts carry source + general knowledge, never per-item
  answers nor text-derived worked examples — `ARCHITECTURE.md` §8.
- **CoT policy**: plain text + per-scene + logic-checked retry on the **checkable** passes;
  CoT is **ON** for the 31B interpretation-bound passes — `reading.py` (uncheckable free
  prose) and `tags.py` (judgment-bound coreference, under §1's two safety conditions).
  The general rule is ARCH §1.
- **Over-marking is acceptable** for the name layer: the downstream consumer tolerates false
  positives; missing a reference is more harmful.
- **Orthography is code's job** (ARCH §12): mechanical quirks (`fix_elision`,
  `normalize_token_brackets`, `unbrace`) are normalized in code and rewritten into the
  conversation history — never requested of the model in the prompt.
- **All LLM calls go through one shared gateway** (`call_llm` in `dante_analyze/llm.py`); `llm7shi` is therefore a
  normal runtime dependency of this package (markup keeps its own structured-output path).
- **The ultimate aim is a knowledge graph** of the poem (entities + who-does-what +
  relations). 03-reading/04-tags produce the referent-resolved material it is built from;
  the registry, speech edges, and relations pass (Active work 1–4) turn that into nodes and
  edges by code joining on tag numbers (ARCH §14). **Not building the graph yet** — current
  work is the upstream formalization/resolution stage. Staged path: Active work 1–4 above.
- **The pipeline is an experiment: how far can a LOCAL LLM analyze the work.** The deliverables
  double as a measurement of capability, so the success criterion is **confirming the current
  accuracy of the automated pipeline, not perfecting the output**. Hence **no hand-proofreading**
  (it would mask the model's true accuracy); 03-reading/04-tags ship as generated and residual
  errors are accepted data. Improving accuracy = changing the *method*, never patching by hand.
  (Mechanism — why the structural checks don't catch WHO-errors — is ARCH §11.)
- **Reading vs. tags = free interpretation vs. tag-anchored formalization** — two passes,
  two kinds of work; don't fold them back together. The reading decides WHO once; tags
  enumerates it under a structural check. Numbered-tag anchoring keeps the formalized
  half verifiable (ARCH §11).

## File structure

| Path | Committed | Description |
|---|---|---|
| `01-scenes/<canticle>/NN.json` | ✓ | Scene ranges + names (committed LLM artifact; built by `01-scenes/scenes.py`) |
| `01-scenes/<canticle>.md` | ✓ | Human-readable scene breakdowns (committed LLM artifact; built by `01-scenes/scenes.py`) |
| `01-scenes/scenes.py` | ✓ | LLM-based scene segmentation builder (dev-only; `uv sync --group dev`) |
| `01-scenes/Makefile` | ✓ | Build target for scene segmentation |
| `pyproject.toml` | ✓ | Package metadata; deps `dante-corpus` + `llm7shi` (both runtime) |
| `ARCHITECTURE.md` | ✓ | Local-LLM scripting patterns shared by every pass here |
| `dante_analyze/__init__.py` | ✓ | Re-exports the shared library public surface |
| `dante_analyze/_paths.py` | ✓ | Anchors the project-root output dirs (01-scenes/ 02-markup/ 03-reading/ 04-tags/) |
| `dante_analyze/corpus.py` | ✓ | Corpus input readers (`read_markup`, `load_scenes`, `available_cantos`) |
| `dante_analyze/checkpoint.py` | ✓ | Per-canto `## Scene` + `# recap` checkpoint I/O; `load_readings`, `load_tags` |
| `dante_analyze/marks.py` | ✓ | Tag numbering (`number_scene`), reply normalizer (`unbrace`), elision repair (`fix_elision`) |
| `dante_analyze/llm.py` | ✓ | Runaway-guarded LLM gateway (`call_llm`), `step_sep`, `MAX_LENGTH`, `LLM_RETRIES` |
| `dante_analyze/prompts.py` | ✓ | Turn-1 prompt builder (`build_reason_prompt`) |
| `dante_analyze/cli.py` | ✓ | Read-only query CLI (`dante-analyze {scenes,reading,tags} show`) |
| `02-markup/markup.py` | ✓ | Per-scene reference markup — single pass, `gemma4:31b-it-qat` + CoT on |
| `02-markup/Makefile` | ✓ | Build target for markup pass |
| `02-markup/<canticle>/NN.txt` | ✓ | Single-pass markup output (committed) |
| `03-reading/reading.py` | ✓ | Free prose reading per scene; CoT on + `gemma4:31b-it-qat`; no check, not proofread |
| `03-reading/Makefile` | ✓ | Build target for reading pass |
| `03-reading/<canticle>/NN.txt` | ✓ | Free reading (committed, not proofread): prose per scene + recap; the checkpoint |
| `04-tags/PLAN.md` | ✓ | Design of the identity-first resolution pass |
| `04-tags/tags.py` | ✓ | Authoritative identity-first `n. Name` resolution per scene (binds direct to reading); reader `gemma4:31b-it-qat`; structure-checked |
| `04-tags/Makefile` | ✓ | Build target for tags pass |
| `04-tags/<canticle>/NN.txt` | ✓ | Per-tag identity resolution (committed, the data downstream consumes); the checkpoint |

The normalized source `.txt`, tokens, and quote-span XML live in **dante-corpus** and are read
through its API. Scene JSON (`01-scenes/<canticle>/NN.json`) lives in this repo.

## Digest edition (future)

Goal: a retelling of each canticle that is **more detailed than a bare plot summary but lighter
than a full line-by-line translation**, at a granularity where the plot can be read as a story.
It is an **analyze-side deliverable** — derived from `03-reading/` (which already resolves WHO per
scene) — not a translation product.

- **Density**: **one to two sentences per scene** — enough to convey who acts and what happens,
  while skipping the dense doctrinal and prosodic detail of the full text.
- **Unit**: scenes are **grouped into paragraphs**, several scenes per paragraph, roughly **3–5
  paragraphs per canto**. A scene is *not* its own paragraph; the per-scene sentences flow
  together into continuous narrative prose.
- **Source of truth**: `03-reading/` carries the referent-resolved prose; the source text and corpus
  scene split (`dante-corpus`) anchor it to the canonical text.
- **Form**: prose paragraphs under `## Canto N` headings.

### Pipeline

The digest is **narrative prose**: it deliberately breaks line fidelity, so it is its own
prose-generation pass with its own check — **narrative coherence + factual accuracy** — not a
coverage/word-table check. Keep it cleanly separate from the translation pipeline.

### Inputs

- `03-reading/<canticle>/NN.txt` — referent-resolved scene readings (primary source of truth).
- `01-scenes/<canticle>/NN.json` — scene ranges for grouping into paragraphs (this repo).
- `01-scenes/inferno.md` / `purgatorio.md` / `paradiso.md` — scene breakdowns (this repo;
  per-scene summaries are *incidental*, not authoritative).

### Deferred

- If a vetted translation later exists it could enrich the digest, but the digest does not
  depend on one.
