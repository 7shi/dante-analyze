# dante-analyze

The formalization / knowledge-graph layer for Dante's *Divine Comedy*. It consumes the
shared corpus from `dante-corpus`, owns the scene segmentation, and runs the LLM analysis passes.

## Premise

Alongside analysing the *Divine Comedy* in its own right, this repository is a methodology
experiment: building know-how for **local-LLM referent resolution that transfers to obscure works**
— texts with no Wikipedia, no annotated edition, no external apparatus to lean on.

Dante is a good proving ground for that method precisely because it is a major work whose every
detail is easy to verify. But that canonical knowledge is used **only for evaluation, never as
input**: no external ground truth (known geography, identities, glossed periphrases) is fed into the
passes. Everything the pipeline asserts
is derived from the source text itself, so the same method can run on a work where no answer key
exists. What is externally known about the poem is an evaluation set the text-derived output is
measured against — not a shortcut poured in.

## Layout

- `dante_analyze/` — shared library (LLM gateway, prompt builders, checkpoint I/O, CLI)
- `01-scenes/` — scene segmentation JSON (committed)
- `02-markup/` — person-reference markup (intermediate)
- `03-reading/` — free prose reading per scene (committed)
- `04-tags/` — `n. Name` identity-first resolution per tag (committed)
- `05-registry/` — canonical KG nodes per figure, with node typing (committed)
- `06-speech/` — speaker per quote span (committed)
- `07-relations/` — event edges per scene (committed)
- `08-kg/` — the assembled per-canticle graph as JSONL (regenerable: `make -C 08-kg`)
- `09-location/` — per-scene current setting (committed)
- `10-topography/` — canonical regions per canticle (committed)
- `11-presence/` — present cast versus merely-mentioned referents per scene (committed)
- `12-addressee/` — addressee per speech span: who each speaker is talking to (committed)
- `13-cohort/` — which class of souls dwells in each scene, with a per-region rollup (committed)
- `ref/` — reference material

## Usage

### Dependency Projects

This project depends on the following companion repository:

- [dante-corpus](https://github.com/7shi/dante-corpus) - The shared corpus library and thin CLI. Serves the normalized Italian source text, tokens, and the quote-span tree as a queryable "DB" through its `dante_corpus` API. **Required** — this project reads canto text from it via an editable path dependency.

### Preparation

Because `dante-analyze` consumes `dante-corpus` via an editable path dependency (`../dante-corpus`), both repositories must share one parent directory. Ensure you have `uv` installed, then clone both into the same directory:

```bash
git clone https://github.com/7shi/dante-analyze.git
git clone https://github.com/7shi/dante-corpus.git
cd dante-analyze
make -C ../dante-corpus
uv sync
```

The resulting layout:

```
your-workspace/
├── dante-corpus/      # source text, tokens (read via the dante_corpus API)
└── dante-analyze/     # this repo (analysis layer)
```

## Generation

```bash
make markup
make reading
make tags
```

## Query

See [`dante_analyze/README.md`](dante_analyze/README.md) for the full CLI and API reference.

```bash
uv run dante-analyze scenes  show inferno 1
uv run dante-analyze reading show inferno 1
uv run dante-analyze tags    show inferno 1
```

## Knowledge graph

The `02-markup → 03-reading → 04-tags` ladder produces the referent-resolved material; four further
passes turn it into a knowledge graph of the poem (entities + who-does-what + relations) by code
joining on the `04-tags` `[n]` tag numbers. All four are **complete and committed for all three
canticles (100 cantos)**; per-pass design and measured results are in each subdir's `README.md`.
See [KG-en.md](KG-en.md) / [KG-ja.md](KG-ja.md) for a walkthrough of the full ladder, and
[KG-PROBLEM.md](KG-PROBLEM.md) for a known limitation (parked).

1. **Registry** (`05-registry/`, LLM) — one canonical, source-spelled node per figure across the
   work, with closed-vocabulary node typing (cached in `types.txt`), set support, and code-extracted
   alias surfaces. → `05-registry/README.md`
2. **Speech** (`06-speech/`, pure code) — speaker per quote span: the unique canonical first-person
   referent in the span's own region, joined onto the registry; else `(unattributed)`. →
   `06-speech/README.md`
3. **Relations** (`07-relations/`, LLM) — event edges per scene (`- [subj] predicate [obj] | frame:
   … | lines a-b`) over a closed 31-predicate vocabulary, citing the `04-tags` `[n]`. →
   `07-relations/README.md`
4. **Assembly** (`08-kg/`, pure code) — joins the relation edges + speaker data into the graph,
   resolving each cited `[n]` through `load_tags` → `load_registry` to a node. Output is per-canticle
   JSONL (`08-kg/<canticle>/{nodes,edges,speech_edges}.jsonl`). → `08-kg/README.md`

```bash
make -C 08-kg                                   # (re)assemble the graph + geometry check
uv run dante-analyze registry  show inferno
uv run dante-analyze speech    show inferno 1
uv run dante-analyze relations show inferno 1
uv run dante-analyze kg        show inferno edges   # part: nodes | edges | speech_edges
```

The speaker/edge data is intended to feed the translation context lock (`dante-dravidian`, below).

## Context lock

The KG is action-only (who-does-what); it carries no **setting**, nor who is bodily present versus
merely named, nor who each speech span is addressed to, nor which class of souls dwells in a place. A
context-lock layer supplies those missing layers, built bottom-up from the text (no external
geography or canon). Five passes are committed for all three canticles (100 cantos); per-pass design
and measured results are in each subdir's `README.md`:

1. **Location** (`09-location/`, LLM) — each scene's current physical setting in the source's own
   place-words, current-setting-only (a merely named, recalled, or compared place is excluded), with
   a source-line basis. → `09-location/README.md`
2. **Topography** (`10-topography/`, LLM + code) — folds those per-scene surfaces into canonical
   **regions** via a positional journey-walk, one region per scene (a piecewise-constant sequence).
   The place analogue of the registry. → `10-topography/README.md`
3. **Presence** (`11-presence/`, code + LLM) — code gathers each scene's already-resolved roster
   (`04-tags` → `05-registry`); the LLM only labels each figure **present** (bodily on stage) or
   **mentioned** (named but absent), with a source-line basis. The person analogue of the
   location/topography split. → `11-presence/README.md`
4. **Addressee** (`12-addressee/`, code + LLM) — for each attributed `06-speech` span, code makes the
   candidate pool = the scene's **present** cast (`11-presence`) minus the speaker, and resolves it
   directly when the pool is empty (`(none)`) or a single figure (`code`); the LLM picks from the
   closed list only when ≥2 present figures remain. The dialogue analogue of the speaker join. →
   `12-addressee/README.md`
5. **Cohort** (`13-cohort/`, code + LLM) — which class of souls dwells in each scene. Code makes the
   candidate set = the scene's **present** cast (`11-presence`) kept to `05-registry` `class`/`generic`
   types, and resolves it directly when empty (no line) or a single class (`code`); the LLM names the
   resident class(es) only when ≥2 remain. `rollup.py` (pure code) then folds the per-scene cohorts
   onto the `10-topography` regions. The narrative-state analogue of topography. → `13-cohort/README.md`

The one remaining pass — a final code join of all layers plus the KG into the per-canto lock — is
planned in `PLAN.md`.

## Downstream Projects

- [dante-dravidian](https://github.com/7shi/dante-dravidian) - A translation of Dante's Divine Comedy into Dravidian languages (Telugu, Tamil, Kannada, and Malayalam) using a structured 4-stage translation process powered by Large Language Models (LLMs).

## Related Previous Projects

- [dante-llm](https://github.com/7shi/dante-llm) - A comparative study of Divine Comedy translation using multiple LLMs (Gemini 1.0 Pro, Gemma 3 27B, GPT-OSS 120B), verifying that locally-runnable models can match Gemini 1.0 Pro quality, with side-by-side comparisons of translations, word tables, and etymology analysis.
- [dante-gemini-25](https://github.com/7shi/dante-gemini-25) - A complete translation of Dante's Divine Comedy using Gemini 2.5 Pro, focusing specifically on English and Japanese translations across the three canticles. This project also includes illustrations generated using Nano Banana (Gemini 2.5 Flash Image Preview) in a classical Renaissance art style inspired by Gustave Doré.
- [dante-gemini](https://github.com/7shi/dante-gemini) - A multilingual exploration of Dante's Divine Comedy using Gemini 1.0 Pro, featuring detailed linguistic analysis of the opening lines in Italian, English, Hindi, Chinese, Ancient Greek, Arabic, Bengali and other languages with word-by-word breakdowns, grammatical details, and etymologies. 
- [dante-la-el](https://github.com/7shi/dante-la-el) - Originally started as a project to transcribe historical Latin and Ancient Greek translations of Dante's Divine Comedy, but evolved into an early LLM experimentation project when AI became the primary focus, exploring computational linguistic analysis methods.
