# 09-location — per-scene local setting (context-lock Step 1)

The first step toward the translation **context lock**. The action-only KG (`08-kg`) represents
who-does-what but carries **no setting** — location is narrative *state*, not an action. This pass
supplies that missing where-layer: for each scene, **where it physically takes place**, in the
work's own terms, with a verifiable source-line basis. It fixes **setting only** — never the
source's meaning or a paraphrase; the `basis` quotes the source as evidence, not interpretation.
The per-scene location *surfaces* it emits
are the input `10-topography` will fold into canonical regions, mirroring the person pipeline
(`04-tags` surface → `05-registry` canonical) applied to places.

This pass exists to keep one judgment per script, so judgments never contaminate each other. It is
a **single text-derived LLM judgment** over the source: it replays no committed reading and uses no
`[n]` tags. Per the repository premise, everything is derived from the text — the prompt never
names the poem's known geography (circles, terraces, spheres); only the place words the text itself
uses. That known structure is `10-topography`'s **evaluation** target, not an input here.

## What it does

Per canticle, per canto, per scene over the plain source (`02-markup` with marks stripped via
`strip_to_source`, each line prefixed with its source line number):

- **Name the current setting.** A single generation turn asks where the scene physically is, over
  its numbered source plus the *setting so far* carried from earlier scenes. Chain-of-thought does
  the where-reasoning in its own channel; `resp.text` is the location lines.
- **Current setting only.** A place merely named, described, foretold, recalled, or used in a
  comparison is *not* the setting (Hell while the scene is still on the slope, Italy, the gate of
  St. Peter); those referred-to places belong to a later referent layer and are excluded.
- **Carry-forward.** A scene that states no place of its own inherits the carried setting,
  emitted with `it: -`. A trailing `# recap` carries the canto's final setting to the next canto.
- **Movement.** A scene may list more than one place (the first is the primary current setting).

Then a per-scene structural check runs; a scene is committed only when it passes (or after the
retry budget is exhausted, kept flagged).

## Inputs / outputs

```
Input:  02-markup/<canticle>/NN.txt   (source lines)
        01-scenes/<canticle>/NN.json  (scene ranges, via load_scenes)
        09-location/<canticle>/N-1.txt recap (carried setting from the previous canto)
Output: 09-location/<canticle>/NN.txt  per-scene location lines + a trailing recap
```

Output is the standard **per-canto checkpoint**: a `## Scene s-e: name` block per scene, the file
itself the resume point (a finished scene is skipped; delete the file to regenerate). Read it with
`load_locations(canticle, canto)` → `{(s, e): [loc, …]}`.

### Scene body — location lines

One line per place, first line the primary current setting:

```
- it: <source place term> | en: <english gloss> | basis: s-e
```

- `it` — the place word(s) **as the text writes them** (the surface `10-topography` folds), or `-`
  when the scene states no place of its own and the setting is carried.
- `en` — a short English gloss of the place.
- `basis` — the source line range within the scene that supports the setting. The full quote is
  recoverable from the line refs at lock-assembly time (`13-lock`), so the checkable core is a line
  reference, not a fragile quoted string.

Example (Inferno 1), showing carry-forward and in-scene movement:

```
## Scene 19-21: Relief from Fear
- it: - | en: foot of a hill | basis: 19-21

## Scene 61-66: A Shadow in the Desert
- it: basso loco | en: low place | basis: 61-61
- it: gran diserto | en: great desert | basis: 64-64
```

## The structural check

Per scene, retried in-conversation (max 3 attempts, last draft kept flagged), **structure only** —
whether the named place is the *right* one is interpretation, shipped as generated (no
hand-proofreading):

- **Well-formed (fatal to the attempt):** at least one line matching the grammar; a line that
  starts like one (`- …`) but fails the grammar is surfaced, not silently dropped.
- **Completeness:** every scene has at least one location (a scene always has a current setting),
  and each line a non-empty `en` gloss.
- **Basis geometry (the strong, total check):** every `basis` range lies within the scene `s..e`.
  This is what catches a model citing a prior scene's lines for a carried setting.
- **`it` in source (soft, warning only):** a stated `it` term that does not occur verbatim in the
  canto source is flagged to stderr — it marks a paraphrase or a carried term, not a failure.

## Model

`ollama:gemma4:31b-it-qat` (the stronger local reader), chain-of-thought **on** by default
(`--no-think` disables): judging the current setting and excluding merely-mentioned places is
reading-heavy, the deliberation stays in Ollama's separate thinking channel, and `call_llm`'s
runaway guard caps the reply.

## Measured result

Full build, all 100 cantos (1796 scenes, 1942 location lines):

- **Every scene passes the structural check** — 0 flagged drafts. The basis-geometry check does
  real work along the way, catching and driving the model to fix settings whose `basis` cited a
  prior scene's lines.
- **Carry-forward dominates as expected:** 1494 scenes (83%) state no place of their own and
  inherit the carried setting (`it: -`); 302 name a place; 116 list more than one for in-scene
  movement.
- **Surfaces are noisy by design:** the 371 place-naming lines use 337 *distinct* `it` surfaces —
  the source keeps shifting its place-words, exactly the variation `10-topography` is meant to fold
  into stable regions.

Spotlight on **Inferno 1** (the canto with a hand-written reference lock, `ref/inferno-01.toml`):

- The reference's source terms surface (`selva oscura`, `piè d'un colle`, `l'erta`, `basso loco`,
  `gran diserto`), with scene 61-66 producing two locations for the in-scene movement.
- The current-vs-mentioned distinction holds: the prophecy scenes (100-129) *name* Italy and Hell
  but list neither as the setting, keeping the carried setting instead.
- The English gloss drifts across a stretch where the source shifts its place-words
  (`la piaggia diserta` → `l'erta` → `loco selvaggio`) — genuine per-scene surfaces, not errors.

## Run

```bash
uv run 09-location/location.py inferno [-c 1] [-m MODEL] [--no-think]
make -C 09-location        # all three canticles
```

The output file is the checkpoint; delete it to regenerate a completed canto.

## Notes

- `load_locations` and `LOCATION_LINE_RE` live in `dante_analyze/checkpoint.py` (alongside
  `load_relations`) — reused parsing belongs in the package, not in a pass script.
- The current-setting vs referred-to-place split is the place analogue of the present-cast vs
  named-but-absent split in the person pipeline; the referred-to places excluded here are picked up
  by the later referent layer, not lost.
