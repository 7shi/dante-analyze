# 04-tags — identity-first per-tag resolution

The reading is the single source of truth for WHO (ARCHITECTURE §11). This pass does not
re-decide referents; it enumerates the reading's identifications into one checkable
`n. Name` line per tag. It binds directly to the committed reading (replayed as the
assistant's reasoning turn), sees nothing else, and is gated by a structural check with
in-conversation retry.

## What was wrong with 05-tags

1. **Identity loss at the seam.** The old rule labeled a figure "the text has not yet named"
   with its in-text epithet. So Scene 121-129 committed `anima` where the reading said
   "a soul (specifically Beatrice)", and Scene 67-75 committed `Poeta` where the reading said
   Virgil — the committed data was strictly *poorer* than the reading it was built from, and
   the downstream registry had to go back to the prose to recover what the pipeline had
   already resolved once.
2. **The orthography clause backfired.** The prompt asked the model to correct malformed
   elisions; the model over-applied it, un-eliding required elisions (`l'altra` → `la altra`),
   creating a standing residual class that required post-hoc repair. A mechanical
   quirk with one canonical form belongs in code, not in the prompt (ARCHITECTURE §12).
3. **Surface forms were the model's job for no reason.** Which words the text uses for a tag
   is already in the markup: `number_scene`'s `meta` carries each tag's `(kind, surface)`.
   Asking the LLM to preserve surface spelling duplicates what code can extract exactly.

## The identity-first rule

For every tag `[1]..[k]`, one line `n. Name`, where Name is the **most specific
identification the reading establishes**, in SOURCE (Italian) spelling:

- The reading identifies a proper name — even one this scene's text has not uttered yet
  ("a soul (specifically Beatrice)", "the mysterious figure (who will be revealed as
  Virgil)") → the proper name: `Beatrice`, `Virgilio`.
- The reading tracks the figure only by epithet (a personification, a beast, a simile
  figure, a generic) → the source-text epithet: `la lupa`, `il veltro`,
  `quei che con lena affannata`, `altrui`.
- The reading itself leaves the tag unidentified → `(unknown)` (reserved for exactly this).
- A tag covering several figures resolves to a comma-separated list on its one line
  (`Cammilla, Eurialo, Turno, Niso`) — downstream parsers must treat the label as a SET.

Never the pronoun surface (`1. io` is wrong; the narrator is `Dante`). No orthography
correction is requested: spelling instructions reduce to "source spelling, the text's own
forms". `fix_elision` runs in code on every parsed label, before the check and before the
reply re-enters the conversation history (§12 — the model never sees its own un-elided
quirk in a prior turn).

Consequence for the registry: per-scene labels are still not guaranteed cross-scene
canonical (a per-unit pass cannot see other units — ARCHITECTURE §11), but the gap is now
only where the *reading itself* doesn't know the identity, instead of every scene where the
text happens not to name the figure.

## Output format

`04-tags/<canticle>/NN.txt`, the standard per-canto checkpoint:

```
# Canto 01 — <title>

## Scene 121-129: The Prohibition of the Ascent
1. Dante
2. Beatrice
3. Virgilio
...
```

Line n = tag [n]. A plain numbered list (not bracketed — `[..]`/`{..}` are the tags' own
markup). Plain text, not JSON (a local Gemma runs away on long structured output). The file
is the checkpoint: finished scenes are skipped on resume; delete the file to regenerate.

## Checks

Per scene, at generation (retry in-conversation, max 3 attempts, last draft kept flagged):

- every tag 1..k named exactly once; nothing extra, nothing empty;
- a pronoun tag must not echo its own surface (via `number_scene`'s `meta`).

The check proves STRUCTURE only. Whether `Beatrice` is the *right* person is interpretation,
inherited from the reading — unverified and shipped as generated, per the project's
no-hand-proofreading policy (root PLAN.md "Decisions to keep").

## What downstream consumes

- `load_tags()` → `{(s, e): {n: name}}` — identity per tag.
- `number_scene()` `meta` → `{n: (kind, surface)}` — surface per tag, no LLM.
- Joining the two gives `(surface, identity)` pairs per scene: the registry's alias input
  (`Poeta`/`ombra` surfaces grouped under the `Virgilio` identity) without a second
  resolution step.

## Model

`ollama:gemma4:31b-it-qat` (the strongest local reader), CoT on by default (`--no-think`
disables): naming a tag is judgment-heavy coreference; the runaway guard (`call_llm`) and
Ollama's separate thinking channel cover the risk (ARCHITECTURE §1).

## Usage

```bash
uv run 04-tags/tags.py inferno [-c 1] [-m MODEL] [--no-think]
make -C 04-tags          # all canticles
```
