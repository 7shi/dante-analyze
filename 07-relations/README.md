# 07-relations — subject–predicate–object edges per scene (KG Step 3)

`03-reading`/`04-tags` resolved WHO each tag is; `05-registry` folded those into canonical nodes;
`06-speech` answered *who is speaking*. This pass answers the remaining KG question — **who does what
to whom** — as line-oriented edges that cite the 04-tags tag numbers, so Step 4 joins them onto the
registry nodes mechanically. It is **interpretation-bound like `04-tags/tags.py`** (CoT on), binds
directly to the committed reading (replayed as the assistant's reasoning turn), and is gated by a
structural check with in-conversation retry.

There are two scripts here. `measure.py` is a **read-only probe** that sized the predicate
vocabulary and froze the design *before* any prompt existed; `relations.py` is the **builder** that
follows the design `measure.py` validated.

## Why a closed predicate vocabulary, and why 31 (measure-first)

ARCHITECTURE §14 requires sizing a closed vocabulary from the full committed output *before*
freezing the prompt. `measure.py` is that probe (pure code, writes nothing): it harvests the
readings' `-s` verbs — every English 3sg-present verb ends in `-s` and the readings are written in
that tense ("Virgil **explains**…", "Dante **asks**…") — then subtracts the two non-predicate
classes that also end in `-s`: plural nouns (`souls`, `spirits`) and **meta-discourse** verbs that
describe the *commentary*, not the events (`describes` 250×, `explains` 247×, `continues` 168×).
Run it to regenerate the evidence:

```
$ uv run 07-relations/measure.py
  ...
  [PASS] closed list ≤ 40 predicates: 31  (the tractability test)
  [info] top-band transitive coverage 58%; the rest is out-of-scope
         (intransitive/state/noun/name) or falls to the `relates-to` residual.
```

The diegetic remainder collapses to **31 canonical predicates** (`CLOSED_VOCAB` in `measure.py`),
which clears the ≤40 tractability gate: **one closed list, no grouping pass** (contrast the
registry's epithet gate, which *failed* — root PLAN.md). The 58% is top-band *transitive* coverage;
the uncovered head is out of scope **by design** — proper names, noun homographs, and
intransitive/state verbs (`appears`, `becomes`, `feels`, `remains`) that are not binary relations.

`CLOSED_VOCAB` is a **human-curated** dictionary (canonical predicate → the measured `-s` surface
synonyms it absorbs), built *from* that diegetic head plus Dante domain knowledge; `measure.py`'s job
is to prove it is the right size and covers the head, not to generate it. It is the **single source
of truth**: `relations.py` does `from measure import CLOSED_VOCAB`, and both the prompt menu and the
structural check read `set(CLOSED_VOCAB)` — there is no second copy.

## What it does

One generation pass per scene, two turns over one conversation (the `tags.py` shape):

1. **Turn 1 — reasoning.** The committed reading is replayed as the assistant turn, over the same
   `number_scene`-tagged scene text `tags.py` used (`build_reason_prompt`, no cross-canto context).
2. **Turn 2 — edges.** `build_relations_prompt` asks for the edge list over that tagged scene.

The cited `[n]` are therefore the **identical** per-scene tag numbers 04-tags resolved against
(`number_scene` is deterministic) — the pass **never renumbers**, which is what makes Step 4's join
total.

### Relation-line grammar

One edge per line, inside the per-scene block:

```
- [<subj>] <predicate> [<obj>] | frame: <literal|simile|prophecy|reported> | lines <a>-<b>
```

- **Both ends are cited tags** `[n]`; `predicate` is one single (hyphenated) token from
  `CLOSED_VOCAB`, or the residual `relates-to` for a genuine binary relation the list doesn't carry.
- **v1 scope: binary person↔being edges only.** An action with no tagged object — movement to a
  *place*, an intransitive/state verb, an attribute — is out of scope; this is also what keeps the
  check total (every end is a tag in the scene's set).
- **`frame` is decided structurally, not post-hoc** (ARCHITECTURE §8): `literal` = a directly
  narrated event; `reported` = the *content* of something a character says/reports; `prophecy` = a
  foretold future event; `simile` = the figurative side of a comparison.
- **No `says-that` meta-edge.** A reported/prophecy/simile proposition is emitted as its **content
  edge** with the matching frame; *who asserted it* is recovered downstream by joining the edge's
  line range to `06-speech`'s quote-span speaker (the literal speech act between two figures —
  `[a] asks [b]` — is itself a normal `literal` edge).

## Output format

`07-relations/<canticle>/NN.txt`, the standard per-canto `## Scene s-e: name` checkpoint, one edge
per line. From the committed `inferno/01.txt` — all four frames occur:

```
## Scene 22-30: The Swimmer Simile
- [3] compares [1] | frame: simile | lines 22-26

## Scene 31-36: The Appearance of the Leopard
- [1] chases [2] | frame: literal | lines 34-34
- [3] chases [2] | frame: literal | lines 35-35

## Scene 67-75: Virgil's Introduction
- [13] praises [14] | frame: reported | lines 73-74

## Scene 112-120: The Plan for the Journey
- [6] guides [4] | frame: prophecy | lines 113-113
```

A scene with no binary relation legitimately produces **zero edges** — an empty block is valid
(unlike `tags.py`, where every tag must be named). The file is the checkpoint: finished scenes are
skipped on resume; delete the file to regenerate. Downstream reads it with
`load_relations(canticle, canto)` → `[{subj, predicate, obj, frame, start, end}, …]` in file order
(`dante_analyze/checkpoint.py`); the scene is recoverable from the line range because scenes
partition the canto.

A single-line relation may be written `lines 81` by the model; the parser accepts it as `81-81` and
`_render` normalizes the committed file to the two-number form, so the strict `RELATIONS_LINE_RE`
that `load_relations` uses never sees the shorthand.

## Checks

Per scene, at generation (retry in-conversation, max 3 attempts, last draft kept flagged) — the four
"all checkable" invariants, plus a malformed-line guard:

1. every cited `[n]` (subject and object) exists in the scene's tag set (`load_tags`, i.e. `1..k`);
2. every `predicate` ∈ `set(CLOSED_VOCAB) ∪ {relates-to}`;
3. every `frame` ∈ `{literal, simile, prophecy, reported}`;
4. every `lines a-b` within the scene range, `a ≤ b`;
5. any line that *looks* like an edge (`- [`) but fails the grammar is flagged — unlike `tags.py`
   there is no completeness backstop (zero edges is valid), so a garbled edge must not vanish
   silently.

The check proves **structure only**. Whether an edge is the *right* relation is interpretation,
inherited from the reading and shipped as generated, per the no-hand-proofreading policy (root
PLAN.md "Decisions to keep"). Two consequences are visible in `inferno/01.txt` and are *accepted
data*, not bugs: Scene 1-12 emits `[1] meets [2]` where both tags are Dante (a self-relation across
distinct tag *numbers* — a "same registry node" filter belongs in Step 4, where node identity is
resolved), and Scene 100-105 (the Veltro) produces no `prophecy` edge though the prose foretells one
— the kind of accuracy the pipeline exists to *measure*.

## Step-4 assembly contract

Each edge carries, as provenance: canticle / canto / scene / cited tag numbers / line range / frame.
Step 4 joins each `[n]` through `04-tags/<canticle>/NN.txt` → the registry canonical node, and — for
`reported`/`prophecy`/`simile` edges — recovers the **asserter** by joining the edge's line range to
the speaker of the containing `06-speech` quote span. `literal` edges are narrated, so they have no
asserter.

## Model

`ollama:gemma4:31b-it-qat` (the strongest local reader), CoT on by default (`--no-think` disables) —
same justification as `tags.py`: relations are judgment-heavy, and the runaway guard (`call_llm`) +
Ollama's separate thinking channel cover the risk (ARCHITECTURE §1).

## Usage

```bash
uv run 07-relations/measure.py                 # the frozen predicate evidence (no LLM)
make -C 07-relations measure                   # same, via make
uv run 07-relations/relations.py inferno [-c 1] [-m MODEL] [--no-think]
make -C 07-relations                           # all three canticles
uv run dante-analyze relations show inferno 1  # read a committed file
```
