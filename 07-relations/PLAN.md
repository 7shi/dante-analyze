# 07-relations — relations pass (Step 3): build spec

> **Status: DESIGN frozen, NOT YET BUILT.** `measure.py` (the predicate probe) is done and
> committed; the closed predicate vocabulary, the relation-line grammar, the structural checks,
> and the wiring are frozen below. The remaining work is `relations.py` (the LLM pass) + the
> wiring + the generation run. Build from this file, then rename it to `README.md` (the subdir
> convention: a pass under construction carries `PLAN.md`, renamed once built — root `PLAN.md`).
>
> Read first, as the template this pass copies: **`04-tags/tags.py` + `04-tags/README.md`**
> (the per-scene, reading-bound, structure-checked formalization shape) and **`ARCHITECTURE.md`**
> §1 (CoT/check), §8 (no answer leakage), §11/§14 (why tag-anchoring is verifiable).

## Pipeline position

```
03-reading/  free prose reading per scene — resolves WHO           [committed, no check]
04-tags/     n. Name identity per tag (number_scene [n])           [structure-checked]
05-registry/ canonical node per figure across the work             [built]
06-speech/   speaker per quote span                                [built]
07-relations/ subject–predicate–object edges per scene (THIS PASS) [to build]
(downstream) Step 4 KG assembly: join [n] → 04-tags → registry node + attach frame/provenance
```

The relations pass produces the KG's **event edges** — *who does what to whom* — that the ladder
still lacks. It is **interpretation-bound like `tags.py`** (CoT ON), binds directly to the
committed reading, and emits edges that cite tag numbers so the downstream join is mechanical.

## Why measure-first (what `measure.py` established)

ARCH §14 mandates sizing the closed vocabulary from the full committed output before freezing the
prompt. `measure.py` harvests the readings' `-s` verbs (every English 3sg-present verb ends in
`-s`, so this catches them all; the work is subtracting plural nouns and **meta-discourse verbs**
— `describes`/`explains`/`notes` — that describe the *commentary*, not diegetic events). The
result:

- The genuine relation predicates collapse to **31 canonical predicates** (≤ 40 — the
  tractability gate PASSes); one closed list, **no grouping pass needed** (contrast the registry's
  failed epithet gate).
- Top-frequency-band coverage ≈ **58%**; the uncovered top-band tokens are out of scope **by
  design** — proper names, noun homographs, and **intransitive/state verbs** (`appears`,
  `becomes`, `feels`, `remains`) that are not binary person↔being relations.

The frozen vocabulary is `measure.py`'s `CLOSED_VOCAB` (canonical predicate → measured `-s`
synonyms). **Source of truth for the predicate list = `CLOSED_VOCAB` in `measure.py`** — the
prompt and the check both read `set(CLOSED_VOCAB)`; do not fork a second copy.

## Pass shape (copy `tags.py`'s two turns)

Per scene, one generation pass over one conversation:

1. **Turn 1 — reasoning.** Replay the committed reading as the assistant turn, exactly as
   `tags.py` does: build the user turn with
   `build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, "", "")` (the same
   `number_scene`-tagged scene text, no cross-canto context), then push the committed reading
   prose (`load_readings`) as the assistant message.
2. **Turn 2 — emit edges.** A new `build_relations_prompt(...)` asks for the edge list over the
   tagged scene. Parse, check, retry in-conversation (max 3, last draft kept flagged) — mirror
   `tags.py`'s `tags_scene` / `_resolve`.

- **CoT ON** by default (`--no-think` disables), model `ollama:gemma4:31b-it-qat`. Justified by
  ARCH §1's two conditions (Ollama routes thinking to its own channel; `call_llm` caps runaway) —
  same as `tags.py`. Add this pass to root `PLAN.md` "Decisions to keep / CoT policy" when built.
- **`[n]` join invariant** (root `PLAN.md` L121–134): the prompt is built on
  `number_scene(lines, s, e)` output — identical to what `tags.py` resolved against — so a cited
  `[n]` is the same tag. **Never renumber.** This is what makes Step 4's join total.
- **No answer leakage** (§8): prompt examples must be **schematic** (`[a] guides [b]`), never an
  edge drawn from the scene under test. Frame selection is defined **structurally in the
  generation rule** (below), not as a post-hoc "verify after" step (§8's selective-check trap).

## Relation-line grammar (frozen)

One edge per line, depth-irrelevant, inside the per-scene block:

```
- [<subj>] <predicate> [<obj>] | frame: <literal|simile|prophecy|reported> | lines <a>-<b>
```

- **Uniform single predicate**; both subject and object are **cited tags** `[n]` (the same
  numbering as 04-tags).
- **v1 scope: binary person↔being edges only** — both ends must be a tagged referent. An action
  with no tagged object (movement to a *place*, an intransitive/state verb, an attribute) is **out
  of scope v1**. This is also what keeps the check total: every end is an `[n]` in the tag set.
- **`frame` (decided): single edge + frame, NO asserter in the line.** A proposition that is
  reported speech / a future prophecy / the figurative side of a simile is emitted as its
  **content edge** with the matching frame; a directly-narrated event is `literal`. There is **no
  `says-that`/`tells` meta-edge wrapping it** — *who asserted it* is recovered downstream by
  joining the edge's line range to `06-speech`'s quote-span speaker (see assembly contract). The
  literal speech act itself, when it is a relation between two figures (`[a] asks [b]`), is a
  normal `literal` edge; the reported *content* of that speech (`[veltro] defeats [lupa]`) is the
  framed edge.
  - Example (schematic): `- [2] defeats [11] | frame: prophecy | lines 100-105`
- **`predicate`** ∈ `set(CLOSED_VOCAB)` (the 31 canonical labels), plus the residual fallback
  **`relates-to`** for a real binary relation whose verb the closed list doesn't carry. Instruct
  the model to prefer a specific predicate and use `relates-to` only as a last resort.

## Structural check (the four "all checkable")

Per scene, at generation, with in-conversation retry (max 3, last draft kept flagged), mirroring
`check_tags`. Returns a list of problems (empty = OK):

1. every cited `[n]` (subject and object) exists in the scene's tag set — `load_tags(canticle,
   canto)[(s, e)]` keys (equivalently `1..k` from `number_scene`);
2. every `predicate` ∈ `set(CLOSED_VOCAB) ∪ {"relates-to"}`;
3. every `frame` ∈ `{literal, simile, prophecy, reported}`;
4. every `lines a-b` within the scene range `[s, e]`, with `a ≤ b`.

No round-trip is possible (edges are new interpretation, not a re-expression of the input), so the
check guards **structure only**; whether the edge is the *right* relation is interpretation,
unverified and shipped as generated (no hand-proofreading — root `PLAN.md` "Decisions to keep").
Unlike `tags.py`, **a scene may legitimately produce zero edges** (no binary relation present) —
an empty edge list passes, and (like `tags.py`'s `k==0`) generation can be skipped only when the
scene has 0 tags; otherwise emit-and-accept-empty.

## Output / checkpoint

`07-relations/<canticle>/NN.txt`, the standard per-canto `## Scene s-e: name` block format
(`render_scene_block` / `append_canto` / `restore_blocks` / `done_scene_ends` from
`checkpoint.py`), one edge per line, **committed**. The file is the checkpoint: finished scenes
skipped on resume; delete to regenerate. Example:

```
# Canto 01 — The Dark Wood and the Encounter with Virgil

## Scene 100-105: The Prophecy of the Veltro
- [2] defeats [11] | frame: prophecy | lines 100-105

## Scene 112-120: The Plan for the Journey
- [1] guides [4] | frame: literal | lines 112-114
```

(Tag numbers above are illustrative of the format, not asserted values.)

## Step-4 assembly contract (note for the downstream join; not built here)

Each edge carries, as provenance: canticle / canto / scene / cited tag numbers / line range /
frame. Step 4 joins each `[n]` through `04-tags/<canticle>/NN.txt` → the registry canonical node,
and — for `reported`/`prophecy`/`simile` edges — recovers the **asserter** by joining the edge's
line range to the speaker of the containing `06-speech` quote span. `literal` edges have no
asserter (they are narrated, not spoken).

## Wiring (build with `relations.py`)

- `dante_analyze/_paths.py`: add `RELATIONS_DIR = ROOT_DIR / "07-relations"`; re-export from
  `dante_analyze/__init__.py`.
- `dante_analyze/checkpoint.py`: add `load_relations(canticle, canto)` → list of
  `{subj, predicate, obj, frame, start, end}` in file order, via a `RELATIONS_LINE_RE`
  (model it on `SPEECH_LINE_RE`). Per-canto, parses each `## Scene` block's edge lines.
- `dante_analyze/cli.py`: add `"relations": RELATIONS_DIR` to `_DIRS` — this gives
  `dante-analyze relations show <canticle> <canto>` for free (the generic `_show` path).
- `07-relations/Makefile`: `include ../model.mk`; `all: uv run relations.py inferno purgatorio
  paradiso -m $(MODEL)` (exactly like `04-tags/Makefile`).

## Usage (once built)

```bash
uv run 07-relations/measure.py                 # the frozen predicate evidence (no LLM)
uv run 07-relations/relations.py inferno [-c 1] [-m MODEL] [--no-think]
make -C 07-relations                           # all canticles
uv run dante-analyze relations show inferno 1
```
