# dante-analyze — KG layer: plan & status (2026-06)

> **▶ STATUS: the ladder scenes → markup → reading → tags is ✓ complete & committed; the registry
> library + measurement are ✓ done; NOW building the knowledge graph (registry → speech → relations
> → assembly). Current step = **Step 1, the registry build** (`05-registry/`): `measure.py` ✓ done,
> `registry.py` ✓ built (epithet-grouping decision resolved as **option A**, v1-skip with
> `grouped: no`). The only LLM work left is the node-typing **generation run**.
>
> **Where to pick up (check this first):**
> - **If `05-registry/{inferno,purgatorio,paradiso}.txt` exist** → Step 1 is DONE (the typing run
>   finished and wrote + structure-checked them). Commit them if not already, then start
>   **Step 2, `06-speech/`** — the next task, fully spec'd below.
> - **If they do not exist yet** → finish the typing run with **`make -C 05-registry`** (already-typed
>   nodes are skipped via the `05-registry/types.txt` cache; rerun is idempotent and safe). It writes
>   the three `<canticle>.txt` and runs the structural check when typing completes, then commit them
>   **together with `05-registry/types.txt`** (the typing record is kept, not transient).
>
> Full Step-1 design is in `05-registry/README.md`. Read `ARCHITECTURE.md` before building or
> changing any pass.**

`dante-analyze` turns the source cantos into referent-resolved structured data — the precursor to a
knowledge graph. It consumes the shared corpus (source lines, tokens, scene ranges, the quote-span
tree) from **`dante-corpus`** via its Python API, and runs local-LLM analysis passes on top. The
patterns every pass shares are written up once in **`ARCHITECTURE.md`**; all LLM calls go through
the single shared gateway `call_llm` (`dante_analyze/llm.py`). The speaker/edge data the KG produces
is intended to feed the translation context lock (`dante-dravidian`).

## Done — don't redo

- **The ladder** `02-markup` → `03-reading` → `04-tags` is complete and committed for all three
  canticles (100 cantos). Design detail lives in each subdir's `README.md` (e.g. `04-tags/README.md`)
  and in `ARCHITECTURE.md` (the formalize-first rationale is ARCH §14).
- **Registry library primitives**, verified across all 1,796 committed scenes with **0 tag-number
  desync** (`number_scene` / `tag_positions` / `load_tags` aligned):
  - `dante_analyze/labels.py` — `norm_label`, `fold_key`, `split_set`, `FIRST_PERSON_{STRONG,WEAK,PLURAL}`.
  - `dante_analyze/marks.py:tag_positions` — column-aware tag positions; mirrors `number_scene`'s
    non-nesting tokenization so tag numbers stay aligned (the 10 corpus-wide nested-brace lines,
    e.g. `{figliuol d'{Anchise}}`, are an accepted ≤1-column anomaly, flaggable by Step 2's
    round-trip assert).
  - `dante_analyze/quotespans.py` — `walk_spans`, `contains`, `own_region` over `QuoteSpan`
    `start_col`/`end_col`.
  - `_paths.py` `REGISTRY_DIR`/`SPEECH_DIR`; all re-exported from `__init__.py`.
- **`05-registry/measure.py`** — pure-code measurement report over the full 04-tags (writes nothing).
- **dante-corpus column extension** — `QuoteSpan.start_col`/`end_col` shipped and editable-installed.
- **Deferred to their steps** (format concrete then): `load_registry` (Step 1) and `load_speech`
  (Step 2) loaders in `checkpoint.py`.

## Measured baselines (what the KG steps build on)

Run `uv run 05-registry/measure.py` to regenerate. Headline numbers over the full committed 04-tags:

- **Registry sizing**: 16,030 tag lines → 2,923 distinct labels → **2,712 nodes** after the
  deterministic `fold_key` code-merge; 157 confirmed sets; 65 `(unknown)`. Identity is well pinned
  for proper-name figures, but the **epithet residual is large**: ~285/312/330 recurring (≥2×)
  non-name epithet nodes per canticle.
- **Decision gates: both FAILED.** Node **typing** is tractable (2,712 nodes, ~20/batch ⇒ ~136
  calls), but the planned single per-canticle **epithet-grouping** call cannot hold ~300 candidates.
  General lesson — measure the consolidation residual on the *full* output, split code-merge from
  LLM residual, prefer flagged singletons over an unverifiable merge — is **ARCH §14**.
- **Speech coverage** (column-aware, via `tag_positions` + `quotespans.own_region`): of **1,222
  quote spans** — strong-unique 395 / multi-strong 28 / weak-only 90 / plural-only 68 / none 641.
  So ~32% resolve to a unique strong first-person speaker by code alone; the rest need the registry's
  canonical speaker labels or accept `(unattributed)`. Columns matter: single-line quotes resolve
  exactly because tag positions carry source columns, not just line numbers.

## KG build steps

### Step 1 — registry build (`05-registry/registry.py`)  [BUILT — typing generation run pending]

`measure.py` ✓ done; `registry.py` ✓ built. It aggregates the `fold_key`-merged nodes (2,922
spellings → **2,711** nodes, `(unknown)` dropped) into one canonical, source-spelled node per figure
across the work, with **node typing** (closed vocabulary), **set** support (`split_set`), and
code-extracted **alias surfaces** (`load_tags` × `number_scene` meta). The epithet-grouping decision
is resolved as **option A** (v1-skip; every non-name node flagged `grouped: no` — a flagged singleton
is safer than an unverifiable merge). The only remaining work is the LLM node-typing generation run
(~128 batched calls, resumable via `05-registry/types.txt`).

**→ Full build spec, output format, structural check, and the option-A rationale live in
`05-registry/README.md`.** `load_registry(canticle)` is added to `checkpoint.py` (format frozen).

### Step 2 — `06-speech/speech.py` (pure code, no LLM)  [NEXT — once Step 1's `<canticle>.txt` are committed]

Consumes the committed registry (speaker = canonical node label); `--raw` flag emits raw labels for
early testing. Build the **raw→canonical map** once from `load_registry`: for each node, `fold_key`
each spelling in its `labels:` list → the node's canonical heading (the same fold the registry built
on, so the join is total); canonicalize every tag's 04-tags label through it *before* the uniqueness
test in steps 3–4. Add `load_speech(canticle, canto)` to `checkpoint.py`. Per canto:

1. `walk_spans(canto.quotes())`; per span its own region (`own_region`, column-aware).
2. Per scene: `tag_positions` + `load_tags` → positioned referents; a tag is in a span by (line,
   col), so single-line quotes resolve exactly. Sanity-assert per line: markup stripped ==
   `canto.line(n).text` (round-trip guard for the column math; the 10 nested-brace lines surface here).
3. Speaker = unique canonical referent of strong first-person tags in the own region; else unique
   weak referent (`signal: weak`); else `(unattributed)`.
4. Flags: `multi(<a>;<b>)` distinct strong referents after canonicalization; `plural` only plural
   1st-person found; `cross-scene` span crosses a scene boundary (canonicalize before the uniqueness
   test). Measured coverage means most spans are `(unattributed)` in v1 — expected, not a bug.

Output `06-speech/<canticle>/NN.txt`, committed; one line per span, depth-first:

```
# Canto 01 — <title>
- 1:65 lines 65-65 | speaker: Virgilio | signal: strong | flags: -
- 1:67 lines 67-78 | speaker: Virgilio | signal: strong | flags: -
- 1:79 lines 79-87 | speaker: (unattributed) | signal: none | flags: -
```

Structural check: file's spans == `canto.quotes()` exactly once each by id; every attributed speaker
exists in the registry.

### Step 3 — Relations pass  [design after Steps 1–2 are built & measured]

The event-edge input the KG still lacks: one LLM pass per scene, bound directly to the reading like
`tags.py`, emitting line-oriented relations with **role-explicit tag citations** (subject before
predicate, object after), a **closed predicate vocabulary**, a **frame marker** (literal / simile /
prophecy / reported), and the covered line range — all four structurally checkable. Example line
format: `- [3] guides [4] | frame: literal | lines 112-114` or
`- [1] says-that [2] defeats [11] | frame: prophecy | lines 100-105`. The closed predicate
vocabulary is to be derived by measuring the readings.

### Step 4 — KG assembly  [last; pure code]

Join relations' tag citations through `04-tags/` to the registry's canonical nodes; attach
provenance (canticle/canto/scene/lines + tag numbers) and frame to every edge; merge the speech
edges. The checks of the upstream passes are what make this join total. JSON is acceptable as a
machine artifact here.

### Wiring (with Steps 1–2)

- Makefiles + `cli.py` entries (`registry show <canticle>`, `speech show <canticle> <canto>`).
  Registry-specific wiring is in `05-registry/README.md`; `06-speech/Makefile` is pure code (no `model.mk`).
- **Convention**: a pass under construction has a `PLAN.md` in its subdir (scope-narrowed build spec);
  once built, rename it to `README.md` (cf. `04-tags/README.md`). Make the new subdir `PLAN.md` in
  that style.

### Verification

```bash
cd /home/7shi/repos/dante-analyze
uv run python -c "import dante_analyze; print('ok')"
uv run 05-registry/measure.py                  # regression: re-confirm the gate numbers
make -C 05-registry                            # Step 1: resume/finish typing + structural check
uv run dante-analyze registry show inferno
# --- Step 2 (06-speech) is NOT built yet; the following apply once it is: ---
# make -C 06-speech
# uv run dante-analyze speech show inferno 1
# spot-check: every speech speaker is a registry node; every 04-tags label is in the registry
```

## Pipeline (data flow)

```
  dante-corpus (shared inputs, via the dante_corpus API — no LLM):
     source cantos ─→ canto.lines() / Line.tokens / canto.quotes()                  [done]

  dante-analyze ladder (committed):
     01-scenes/<c>/NN.json → 02-markup → 03-reading → 04-tags/<c>/NN.txt             [done]
        (markup round-trip-checked; reading free prose, no check; tags identity-first, structure-checked)
     05-registry/measure.py → stdout report (registry sizing + gates, pure code)     [done]

  KG build (next — this plan):
     05-registry/registry.py → 05-registry/<c>.txt      canonical nodes + types      [Step 1]
     06-speech/speech.py     → 06-speech/<c>/NN.txt      speaker per quote span       [Step 2]
     (relations)             → TBD                       schema edges per scene       [Step 3]
     (assembly)              → TBD                       the joined graph             [Step 4]
```

## Decisions to keep

- **Source-spelling names** everywhere (`Virgilio`, not "Virgil"), **identity-first**: the committed
  label is the most specific identification the reading establishes, never a scene-local epithet for
  a figure the reading already names (ARCH §11).
- **No answer leakage**: prompts carry source + general knowledge, never per-item answers nor
  text-derived worked examples — `ARCHITECTURE.md` §8.
- **CoT policy**: plain text + per-scene + logic-checked retry on the **checkable** passes; CoT is
  **ON** for the 31B interpretation-bound passes — `reading.py` (uncheckable free prose) and
  `tags.py` (judgment-bound coreference, under §1's two safety conditions). The general rule is ARCH §1.
- **Over-marking is acceptable** for the name layer: the downstream consumer tolerates false
  positives; missing a reference is more harmful.
- **Orthography is code's job** (ARCH §12): mechanical quirks (`fix_elision`,
  `normalize_token_brackets`, `unbrace`) are normalized in code and rewritten into the conversation
  history — never requested of the model in the prompt.
- **All LLM calls go through one shared gateway** (`call_llm` in `dante_analyze/llm.py`); `llm7shi`
  is therefore a normal runtime dependency of this package (markup keeps its own structured-output path).
- **The ultimate aim is a knowledge graph** of the poem (entities + who-does-what + relations).
  03-reading/04-tags produce the referent-resolved material; the registry, speech edges, and
  relations pass turn that into nodes and edges by code joining on tag numbers (ARCH §14).
- **The pipeline is an experiment: how far can a LOCAL LLM analyze the work.** The deliverables
  double as a measurement of capability, so the success criterion is **confirming the current
  accuracy of the automated pipeline, not perfecting the output**. Hence **no hand-proofreading**
  (it would mask the model's true accuracy); 03-reading/04-tags ship as generated and residual errors
  are accepted data. Improving accuracy = changing the *method*, never patching by hand. (Mechanism
  — why the structural checks don't catch WHO-errors — is ARCH §11.)
- **Reading vs. tags = free interpretation vs. tag-anchored formalization** — two passes, two kinds
  of work; don't fold them back together. The reading decides WHO once; tags enumerates it under a
  structural check. Numbered-tag anchoring keeps the formalized half verifiable (ARCH §11).

## Deferred

- **Pronoun-layer marking quality** — local models still make errors on Inferno 1: spurious/misplaced
  `[+pron]` supply (needs clause parsing), non-pronoun bracketed, wrong pronoun category/form. The
  hard classes need a stronger model; the partly-checkable classes are deferred pending a reliable
  pronoun lexicon.
- **Remaining pronoun-layer logic checks** — misplaced-supply detection (`[+..]` not immediately
  before a verb); nominative-only supplied-pronoun check. Both need a pronoun lexicon.
- **Diff-only storage** — store only additions vs. the source token list.

## File structure

| Path | Committed | Description |
|---|---|---|
| `01-scenes/<canticle>/NN.json` | ✓ | Scene ranges + names (committed LLM artifact; built by `01-scenes/scenes.py`) |
| `01-scenes/<canticle>.md` | ✓ | Human-readable scene breakdowns (committed LLM artifact) |
| `01-scenes/scenes.py` | ✓ | LLM-based scene segmentation builder (dev-only; `uv sync --group dev`) |
| `01-scenes/Makefile` | ✓ | Build target for scene segmentation |
| `pyproject.toml` | ✓ | Package metadata; deps `dante-corpus` + `llm7shi` (both runtime) |
| `ARCHITECTURE.md` | ✓ | Local-LLM scripting patterns shared by every pass here |
| `dante_analyze/__init__.py` | ✓ | Re-exports the shared library public surface |
| `dante_analyze/_paths.py` | ✓ | Anchors the project-root output dirs (01-scenes/ … 04-tags/ 05-registry/ 06-speech/) |
| `dante_analyze/corpus.py` | ✓ | Corpus input readers (`read_markup`, `load_scenes`, `available_cantos`) |
| `dante_analyze/checkpoint.py` | ✓ | Per-canto `## Scene` + `# recap` checkpoint I/O; `load_readings`, `load_tags` |
| `dante_analyze/marks.py` | ✓ | Tag numbering (`number_scene`), column-aware tag positions (`tag_positions`), reply normalizer (`unbrace`), elision repair (`fix_elision`) |
| `dante_analyze/labels.py` | ✓ | Label normalization/classification: `norm_label`, `fold_key`, `split_set`, first-person surface sets (registry) |
| `dante_analyze/quotespans.py` | ✓ | Quote-span geometry over dante_corpus `QuoteSpan`: `walk_spans`, `contains`, `own_region` (speech) |
| `dante_analyze/llm.py` | ✓ | Runaway-guarded LLM gateway (`call_llm`), `step_sep`, `MAX_LENGTH`, `LLM_RETRIES` |
| `dante_analyze/prompts.py` | ✓ | Turn-1 prompt builder (`build_reason_prompt`) |
| `dante_analyze/cli.py` | ✓ | Read-only query CLI (`dante-analyze {scenes,reading,tags,registry} show`) |
| `02-markup/markup.py`, `Makefile`, `<canticle>/NN.txt` | ✓ | Per-scene reference markup (single pass, `gemma4:31b-it-qat` + CoT on) + output |
| `03-reading/reading.py`, `Makefile`, `<canticle>/NN.txt` | ✓ | Free prose reading per scene (CoT on; no check, not proofread) + output |
| `04-tags/README.md`, `tags.py`, `Makefile`, `<canticle>/NN.txt` | ✓ | Identity-first `n. Name` resolution (binds to reading; structure-checked) + design doc + output |
| `05-registry/measure.py` | ✓ | Pure-code measurement report over 04-tags + Step-3 decision gates (no LLM, writes nothing) |
| `05-registry/README.md` | ✓ | Step 1 design doc: `measure.py`/`registry.py` purpose, make targets, output format, option A |
| `05-registry/registry.py`, `Makefile` | ✓ | Registry build (Step 1, option A); typing cached in `types.txt`, resumable |
| `05-registry/<canticle>.txt` | — | Canonical node table — produced by the typing generation run |
| `06-speech/speech.py`, `<canticle>/NN.txt`, `PLAN.md`, `Makefile` | — | Speech edges (Step 2) — to come |

The normalized source `.txt`, tokens, and quote-span XML live in **dante-corpus** and are read
through its API. Scene JSON (`01-scenes/<canticle>/NN.json`) lives in this repo.

## Digest edition (future)

Goal: a retelling of each canticle that is **more detailed than a bare plot summary but lighter than
a full line-by-line translation**, at a granularity where the plot can be read as a story. It is an
**analyze-side deliverable** — derived from `03-reading/` (which already resolves WHO per scene) —
not a translation product. Deferred until after the KG.

- **Density**: **one to two sentences per scene** — enough to convey who acts and what happens, while
  skipping the dense doctrinal and prosodic detail of the full text.
- **Unit**: scenes are **grouped into paragraphs**, several scenes per paragraph, roughly **3–5
  paragraphs per canto**. A scene is *not* its own paragraph; the per-scene sentences flow together
  into continuous narrative prose.
- **Source of truth**: `03-reading/` carries the referent-resolved prose; the source text and corpus
  scene split (`dante-corpus`) anchor it to the canonical text.
- **Form**: prose paragraphs under `## Canto N` headings. It deliberately breaks line fidelity, so it
  is its own prose-generation pass with its own check — **narrative coherence + factual accuracy** —
  not a coverage/word-table check. Keep it cleanly separate from the translation pipeline.
- **Inputs**: `03-reading/<canticle>/NN.txt` (primary), `01-scenes/<canticle>/NN.json` (paragraph
  grouping), `01-scenes/<canticle>.md` (incidental, not authoritative). A vetted translation, if one
  later exists, could enrich it but is not a dependency.
