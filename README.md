# dante-analyze

The formalization / knowledge-graph layer for Dante's *Divine Comedy*. It consumes the
shared corpus from `dante-corpus`, owns the scene segmentation, and runs the LLM analysis passes.

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

## Downstream Projects

- [dante-dravidian](https://github.com/7shi/dante-dravidian) - A translation of Dante's Divine Comedy into Dravidian languages (Telugu, Tamil, Kannada, and Malayalam) using a structured 4-stage translation process powered by Large Language Models (LLMs).

## Related Previous Projects

- [dante-llm](https://github.com/7shi/dante-llm) - A comparative study of Divine Comedy translation using multiple LLMs (Gemini 1.0 Pro, Gemma 3 27B, GPT-OSS 120B), verifying that locally-runnable models can match Gemini 1.0 Pro quality, with side-by-side comparisons of translations, word tables, and etymology analysis.
- [dante-gemini-25](https://github.com/7shi/dante-gemini-25) - A complete translation of Dante's Divine Comedy using Gemini 2.5 Pro, focusing specifically on English and Japanese translations across the three canticles. This project also includes illustrations generated using Nano Banana (Gemini 2.5 Flash Image Preview) in a classical Renaissance art style inspired by Gustave Doré.
- [dante-gemini](https://github.com/7shi/dante-gemini) - A multilingual exploration of Dante's Divine Comedy using Gemini 1.0 Pro, featuring detailed linguistic analysis of the opening lines in Italian, English, Hindi, Chinese, Ancient Greek, Arabic, Bengali and other languages with word-by-word breakdowns, grammatical details, and etymologies. 
- [dante-la-el](https://github.com/7shi/dante-la-el) - Originally started as a project to transcribe historical Latin and Ancient Greek translations of Dante's Divine Comedy, but evolved into an early LLM experimentation project when AI became the primary focus, exploring computational linguistic analysis methods.
