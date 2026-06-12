# dante-analyze

The formalization / knowledge-graph layer for Dante's *Divine Comedy*. It consumes the
shared corpus from `dante-corpus`, owns the scene segmentation, and runs the LLM analysis passes.

## Layout

- `dante_analyze/` — shared library (LLM gateway, prompt builders, checkpoint I/O, CLI)
- `01-scenes/` — scene segmentation JSON (committed)
- `02-markup/` — person-reference markup (intermediate)
- `03-reading/` — free prose reading per scene (committed)
- `04-tags/` — `n. Name` identity-first resolution per tag (committed)
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

## Downstream Projects

- [dante-dravidian](https://github.com/7shi/dante-dravidian) - A translation of Dante's Divine Comedy into Dravidian languages (Telugu, Tamil, Kannada, and Malayalam) using a structured 4-stage translation process powered by Large Language Models (LLMs).

## Related Previous Projects

- [dante-llm](https://github.com/7shi/dante-llm) - A comparative study of Divine Comedy translation using multiple LLMs (Gemini 1.0 Pro, Gemma 3 27B, GPT-OSS 120B), verifying that locally-runnable models can match Gemini 1.0 Pro quality, with side-by-side comparisons of translations, word tables, and etymology analysis.
- [dante-gemini-25](https://github.com/7shi/dante-gemini-25) - A complete translation of Dante's Divine Comedy using Gemini 2.5 Pro, focusing specifically on English and Japanese translations across the three canticles. This project also includes illustrations generated using Nano Banana (Gemini 2.5 Flash Image Preview) in a classical Renaissance art style inspired by Gustave Doré.
- [dante-gemini](https://github.com/7shi/dante-gemini) - A multilingual exploration of Dante's Divine Comedy using Gemini 1.0 Pro, featuring detailed linguistic analysis of the opening lines in Italian, English, Hindi, Chinese, Ancient Greek, Arabic, Bengali and other languages with word-by-word breakdowns, grammatical details, and etymologies. 
- [dante-la-el](https://github.com/7shi/dante-la-el) - Originally started as a project to transcribe historical Latin and Ancient Greek translations of Dante's Divine Comedy, but evolved into an early LLM experimentation project when AI became the primary focus, exploring computational linguistic analysis methods.
