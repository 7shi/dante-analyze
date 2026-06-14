# 03-reading — free prose reading per scene

This is the **free-interpretation** pass and the single source of truth for WHO (ARCHITECTURE §11).
For each scene it writes a plain-English reading — who does what, who speaks to whom, and, for every
numbered `[n]` tag in the markup, which person it refers to. The companion pass `04-tags` does **not**
re-decide referents; it replays this reading as its reasoning turn and merely enumerates the
identifications into one checkable `n. Name` line per tag. Deciding WHO once here, then formalizing it
under a structural check there, is the deliberate split between *interpretation* and *tag-anchored
formalization* (root PLAN.md "Decisions to keep").

## What it does

One generation per scene (`build_reason_prompt`, `gemma4:31b-it-qat`, CoT on by default, via
`call_llm`). The reading of earlier scenes this canto plus a short `# recap` carried from the
previous canto are given as context, so prior figures are nameable. At the end of each canto a fresh
1–3 line `# recap` of the end-state is written for the next canto.

## Output

`03-reading/<canticle>/NN.txt` — a `## Scene s-e: name` prose block per scene (the reading, then a
`**Tag Resolutions**` list pairing each `[n]` to a person), and a trailing `# recap`. The file is the
checkpoint: a scene with a non-empty body is skipped on resume; an empty generation **aborts** rather
than commit a blank scene. From `inferno/01.txt`:

```
## Scene 1-12: Lost in the Dark Wood
In this opening scene, the narrator discovers himself lost in a "dark wood" (*selva oscura*). ...
He establishes that he will tell the reader about the things he saw there ...

The speaker throughout this entire passage is the narrator and protagonist, Dante.

**Tag Resolutions:**
* [1]: Dante
* [2]: Dante
...

# recap
- Dante and Virgil are now traveling together.
- They are departing the dark wood to begin their journey through the afterlife.
```

## No check (by design)

Free prose is not tag-anchored — there is no round-trip and no coverage anchor — so this pass carries
**no logic check**; it is committed as generated. Whether the reading is *correct* is unverified, and
residual errors are **accepted data**, not patched by hand: the pipeline is an experiment in how far a
local LLM can analyze the work, so hand-proofreading would mask the model's true accuracy. Accuracy is
improved by changing the *method*, never by per-item edits (root PLAN.md "Decisions to keep";
ARCHITECTURE §11). `04-tags`'s structural check is what re-grounds this prose to the numbered tags.

## Model

`ollama:gemma4:31b-it-qat` (the stronger reader — precision over speed), CoT on by default
(`--no-think` disables): this is the uncheckable, precision-critical layer, so the model is allowed to
think, and there is no structured output for CoT to corrupt — the thinking stays internal, the saved
text is clean prose (ARCHITECTURE §1).

## Usage

```bash
make -C 03-reading                             # all three canticles
uv run 03-reading/reading.py inferno [-c 1] [-m MODEL] [--no-think]
uv run dante-analyze reading show inferno 1    # read a committed file
```

Downstream reads it with `load_readings(canticle, canto)` → `{(s, e): prose}`
(`dante_analyze/checkpoint.py`); `04-tags/tags.py` replays that prose as its assistant reasoning turn.
