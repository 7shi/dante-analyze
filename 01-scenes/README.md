# 01-scenes — scene segmentation per canto

This is the **first analysis pass** and the one every later pass is keyed to: it cuts each canto into
ordered, gap-free **scenes**, the unit the whole pipeline iterates over. Every downstream pass loads
this split with `load_scenes(canticle, canto)` → `(canto_title, [(start, end, scene_name), …])`, so
the scene boundaries decided here fix the granularity of markup, reading, tags, and the KG.

It is a **regenerate-only** builder: the segmentation is committed, so a normal run of the pipeline
never re-invokes it (no special dependencies — the standard `uv sync` is enough). It reads the source
straight from `dante-corpus` (no upstream analysis pass).

## What it does

One generation per canto, two turns over a shared conversation (`split_canto`):

1. **Turn 1 — planning (CoT on).** Over the line-numbered canto, the model reasons in free prose
   about where the natural scene boundaries fall — a shift of place, speaker, action, or topic.
2. **Turn 2 — structured output.** It turns that reasoning into a `CantoBreakdown` (a `pydantic`
   schema: `canto_title` + `scenes[]` of `start_line, end_line, scene_name, summary`), via llm7shi's
   `generate_with_schema`. This is the project's one **structured-output** pass — it does not use the
   plaintext `call_llm` gateway the other passes share.

**Fine granularity is intended.** The prompt asks for ~10–18 lines per scene (a canto of N lines →
roughly N/15 scenes *or more*) and to over-split whenever a passage is borderline: merging two
adjacent scenes downstream is trivial, but splitting one later would force a re-read. Default model
is `ollama:gemma4:26b` (segmentation is lighter than the 31B reading work).

## Output

Two committed artifacts per canticle. The per-canto JSON is the machine checkpoint that `load_scenes`
reads; the `.md` is the human-readable roll-up.

`01-scenes/<canticle>/NN.json` — one canto, the checkpoint (a canto already present is skipped on
resume):

```json
{
  "canto_title": "The Dark Wood and the Encounter with Virgil",
  "scenes": [
    { "start_line": 1,  "end_line": 12, "scene_name": "Lost in the Dark Wood",
      "summary": "Dante describes his state of spiritual confusion and how he lost the straight path in a dark forest." },
    { "start_line": 13, "end_line": 18, "scene_name": "The Sight of the Sunlit Hill",
      "summary": "Dante reaches the foot of a hill and sees its summit illuminated by the rays of the sun." }
  ]
}
```

`01-scenes/<canticle>.md` — every canto as a table:

```
## Canto 1: The Dark Wood and the Encounter with Virgil

| Lines | Scene | Summary |
|---|---|---|
| 1-12 | Lost in the Dark Wood | Dante describes his state of spiritual confusion and how he lost the straight path in a dark forest. |
| 13-18 | The Sight of the Sunlit Hill | Dante reaches the foot of a hill and sees its summit illuminated by the rays of the sun. |
```

`01-scenes/ref/` holds reference scene breakdowns (`AGENTS.md` policy + the `*-ja.md` Japanese
breakdowns) used while developing the prompt — reference material, not generated output.

## Check

`check_ranges` validates each canto's scenes structurally: no reversed range, no gap, no overlap,
and the scenes together cover line 1 to the source's last line. Only **Turn 2** is retried on
failure (the specific problems fed back), max 3 attempts; after that the run **aborts** (`sys.exit`)
rather than commit a malformed split — segmentation is the spine every later pass depends on, so a
bad canto must not be written. The `scene_name`/`summary` text itself is interpretation and ships as
generated.

## Usage

```bash
make -C 01-scenes                                      # all three canticles → <canticle>.md + NN.json
uv run 01-scenes/scenes.py inferno --outdir .          # one canticle
uv run 01-scenes/scenes.py inferno -c 1 -o /tmp/x.md   # one canto (testing)
uv run dante-analyze scenes show inferno 1             # read a committed canto
```

Downstream reads it with `load_scenes(canticle, canto)` → `(canto_title, [(start, end, name), …])`
(`dante_analyze/corpus.py`).
