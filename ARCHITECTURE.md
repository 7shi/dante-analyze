# Local-LLM scripting patterns (read before building a new pass)

The analysis scripts here (`01-scenes/scenes.py`, `02-markup/markup.py`, `03-reading/reading.py`, `04-tags/tags.py`) drive a
**local LLM** (Ollama, e.g. Gemma) over Dante's text. Local models are weaker than hosted ones and fail in
characteristic ways: they **loop**, **truncate**, **drift into unrelated output
mid-reply**, and **run away** during long free generation. The patterns below were
learned the hard way on this project; apply them from the start in any new
local-LLM script, rather than rediscovering them.

The guiding stance: **don't trust the model's judgment — trust a logic check.** The
model proposes; your code disposes. Everything else follows from that.

## 1. No CoT. Output something your code can verify, then retry.

Chain-of-thought on a local model is **slow** (minutes per call, ~100 min/canto in
one early experiment here) and **prone to runaway**, for a marginal quality gain.
Disable thinking (`include_thoughts=False`, or the model's `--no-think`).

**The danger is CoT colliding with *checkable* output** — the model loops or truncates
the very form your check reads — so the rule is firmest where output is checkable. Two
cases relax it:

- **Uncheckable free prose** (e.g. `reading.py`, §11) has nothing for CoT to corrupt:
  the thinking stays internal, the saved text is plain prose. When such a layer is also
  precision-critical and unproofread — generation being its only quality lever (§11) —
  turn CoT **on** (with a larger model), trading speed for interpretation quality.
- **A checked pass where two conditions defuse the collision**: (1) the backend routes
  thinking to a separate channel (Ollama `think=True`; caveat below), so deliberation
  never intermixes with the checkable text (`resp.text` stays clean); and (2) a runaway
  guard caps generation (`call_llm`'s length limit), so a looping CoT is cut off rather
  than eating the output. With both, CoT-on pays off even though the form is checked —
  which is why `tags.py` (judgment-bound resolution, structure-checked) runs CoT on.

Default off; turn it on deliberately, and only in those two cases.

**Backend caveat: not every backend can actually turn CoT off.** Ollama honours
`think=False` (`include_thoughts=False`). A *hosted* Gemma (Google backend, e.g.
`google:gemma-4-31b-it`) does **not** — asking it to disable thinking just makes it
**leak the reasoning into the body** (prompt-echo, self-questions, multiple drafts all
land in `resp.text`). So on such a backend CoT-off is the worst option: you get the
mess of thinking without a clean answer channel. There, turn `include_thoughts=True`
even for a simple step (e.g. reading.py's recap) — thinking then routes to its own
channel and `resp.text` is clean — and lean on a forgiving parse (`parse_bullets`
keeps only `- ` lines) plus, where it matters, a logic check.

Instead, design the task so the **output itself is checkable deterministically**,
and retry on failure. Prefer a check that needs **no whitelist and loses no
information** — e.g. `markup.py` only adds `[..]`/`[+..]`/`{..}` markup, so stripping
the markup must reproduce the input line verbatim (a *round-trip*). That proves
faithfulness without the code ever judging *which* words were marked. When a
round-trip isn't possible, use a structural/consistency check (e.g. a per-id
table: every id present exactly once, no unknown id, no empty value).

## 2. When deliberation is genuinely needed, split it across turns — never CoT-in-output.

Mixing reasoning with the final/structured output is exactly what makes a local
Gemma loop or truncate (see memory `gemma-cot-plaintext`). If the model must
"think", give it a turn to do so in **plain free prose with no other job**, then a
**second turn** (same conversation) to emit the result using that reasoning:

- Turn 1 — free-form critique/analysis only, no rewrite, no schema.
- Turn 2 — the actual output (plain text or structured), now informed by turn 1.

This is the shape of `scenes.py` (planning turn → structured turn) and of `tags.py`
(reasoning turn → checkable resolution turn).

**When the deliberation prose is itself a deliverable, promote it to its own script
and committed artifact.** The reasoning turn need not stay throwaway scratch context.
`reading.py` is exactly such a Turn 1 (a free English reading of the scene) promoted
to a committed file; `tags.py` then **replays that reading as the assistant's
reasoning turn** before its checkable turn. Same split-the-turns shape, but the
deliberation is now a committed, inspectable, reusable output in its own right —
amenable to proofreading if one chooses, though this project ships it as generated (§11).

## 3. One narrow task per call. Split compound work.

Do not ask a local model to detect + resolve + rewrite + extract at once — quality
collapses and output pollutes (an early roster experiment conflated non-persons,
periphrases, and absent exempla because one call did everything). Decompose:

- `markup.py` marks references **only** (pronouns, then names) — no resolution; both
  layers run in a **single call** (pronoun `[..]`/`[+..]` and name `{..}` simultaneously).
- a roster/extraction pass should split **rewrite** (stage 1) from **extract** (stage 2).

Each call has one job with one kind of check.

**Keep the mark criterion simple.** When the scope definition has complex sub-clauses
(e.g. "only persons who appear as characters in this canto"), the model must make
inference calls that are hard to get right. A broader, simpler criterion with
**over-marking tolerance** is more reliable: the downstream step can handle false
positives, but false negatives (missed marks) are harder to recover. Only add
exclusions that are unambiguous and structurally checkable.

**How finely you must split is a function of the model tier, not of the task — so treat
the decomposition as provisional.** The narrow-task / small-unit splitting above (and the
multi-pass ladder of §14) exists because *current* local models are weak; it is the cheapest
*reliable* decomposition for this capability tier, not an intrinsic property of the work. A
stronger model can hold more at once — several of these steps could collapse into one pass, or
intermediate scaffolding be dropped, with no loss. So don't reify the current step count: when the
model tier improves, **re-measure whether a simpler pipeline holds the same accuracy** (the
checks make this cheap to test) rather than preserving granularity out of habit. Split as much as
today's model needs, and no more.

## 4. Work in small units (per scene), not whole cantos.

Short replies keep a local model from drifting into unrelated text mid-reply.
Process one **scene** per call (ranges from `01-scenes/<canticle>/NN.json`), which also
gives a coherent dramatic beat. A canto is the checkpoint granularity; a scene is
the call granularity.

## 5. Accumulate validated results; retry only the failures, pinpointed.

Never regenerate work that already passed. Across retry turns:

- **Accumulate** the items (lines/ids) that validated; keep them.
- Re-request **only the still-failing** items, identified by number + source, as a
  **follow-up turn in the same conversation** (reuse prior context, don't restart).
- A few bad items must not force regenerating the whole unit.

Layer a coarse and a fine retry: scene-level follow-ups, then a **per-item redo** in
a fresh session with a small surrounding-context window for anything still failing.
Whatever never validates is left unmarked and **flagged** in the output (e.g. a
leading `*`), not silently wrong.

## 6. Prefer a stronger generation pass to a review pass.

The reflex for catching a generator's errors is a second-model review pass; on this
project that proved the wrong default. **Spend on generation first (model size, CoT,
§1/§13), and add a review pass only for what a strong single pass still misses.**
`markup.py` was originally an under-powered (CoT-off) draft + a second-model round-trip
review; the review was mostly compensating for the weak generator. The refactor dropped
it — `markup.py` now runs the **31B reader with CoT on** as a single pass, the round-trip
check polices every line, and `normalize_token_brackets` canonicalizes bracket edges
before the check (§12). No pass here carries a second-model review.

If you do add one, the constraints are:

- **Run it cold, in a fresh session** — a self-review that inherits the generation
  conversation defends its own draft. Show *source + draft* only; keep examples
  schematic (§8).
- **Re-validate every correction with the same logic check**, so review can only
  improve: a correction that fails the check is discarded. But the check guards
  *faithfulness, not quality* — a round-trip proves marks were added/removed correctly,
  not that the *right* things were marked, so review can still wrongly add/remove valid
  marks. Monitor its net effect (diff the checkpoints).
- **The reviewer must be at least as strong a *reader* as the generator.** A
  complementary smaller/faster model can catch mechanical errors on a checkable task,
  but on an *interpretation* task a weaker reader confidently rewrites correct readings
  into wrong ones (§11) — worse than no review. Interpretation critique needs a reader at
  least as capable as the generator (the same model, a larger one, or a human).
- **Enumerate known error classes** in the prompt (a `Watch especially for:` list) — a
  generic "find mistakes" yields vague critique.

## 7. Guard runaway at the call boundary (a `call_llm` wrapper).

Wrap the raw generate call: cap the reply (`max_length`, e.g. 10000 chars) and
detect repetition; on a hit, **regenerate** (runaway is stochastic, so a fresh draw
usually recovers). This mechanical guard sits **under** the validation retries of
§5: `call_llm` fixes loops/truncation; the outer loop fixes content. Two distinct
layers — don't conflate them.

## 8. No answer leakage in prompts.

Examples in a prompt must be **schematic**, never drawn from the very text under
test — concrete worked examples taken from the canto being processed are *cheating*
(they inflate results and teach the specific answer). The prompt may carry the
**source text (input)** and **general knowledge of the work**, but never the
per-item answer, nor a text-derived example that reveals how a specific line/quote
should come out.

**A post-hoc "verify after placing" instruction is applied selectively — the model
skips lines it considers already correct.** If a rule involves positional placement
(e.g. "insert X just before the verb"), the model commits to a position early and
does not re-examine it unless prompted to. A trailing check step ("if the result is
not grammatical, move it") fires only on lines the model suspects are wrong, which
is not all lines. The reliable fix: define the position structurally in the generation
rule itself — describe where the element belongs in terms of the sentence's constituents
(e.g. "before the entire preverbal clitic cluster, not inside it"), so the correct
position is produced on the first pass rather than corrected by a self-check that
runs selectively.

## 9. The output file is the checkpoint.

Make a full run **skip** any canto whose output already exists, so an interrupted
run resumes and hand edits survive. Offer a test mode (`-c CANTO`) that regenerates
one unit.

## 10. Log a long local run so progress is legible.

A canticle run is long; the log is how you supervise it. Conventions used here:

- Stream the model's raw output to **stdout**; status/diagnostics to **stderr**.
- Print a **step separator** (e.g. `--- reading ---`, `--- recap ---`,
  `--- tags resolution ---`) before each step.
- Print a **final verdict per unit** — `OK — all N validated` vs
  `NOT resolved — lines [...] still failing` — so resolved vs. abandoned is
  readable from the log alone (don't make the reader infer it).
- On retry, log *why* (the failing check's message), not just a count.
- Flag unresolved items in the final output itself.

## 11. Anchor a free generative layer to numbered tags so coverage stays checkable.

Some passes can't round-trip: resolving each marked reference of a scene to the person
it stands for is an *interpretation*, which no logic check can verify (is `io` here
Dante or the enclosing speaker?). This work is **split across scripts at the checkable
seam**. `reading.py` does the pure interpretation as free prose — uncheckable, so no
machine check (it ships as generated; see below). `tags.py` then re-grounds that reading
to the marks. Do not give up on a check on the checkable half; **anchor the formalized
output to the marks**. Number every mark in the unit (`[1:io]`, `{4:Virgilio}`,
deterministically) and emit one numbered `n. Name` line per tag. Then a check stands
even though the prose is free: every tag named exactly once, none extra or empty
(nothing dropped, nothing invented). A cheap lexical guard also catches a
*non*-resolution — a pronoun tag whose `n. Name` line merely echoes the pronoun
surface (`1. io`) rather than naming a person. This is the round-trip principle (§1)
carried to a layer that can't round-trip — the check guards *coverage and structure*;
the interpretation it cannot verify is **left unverified** and shipped, an accepted residual.

A §6 review on a free-text layer is hard to make pay, so **neither interpretation pass
carries one**. A full re-emission has no round-trip constraint, so the reviewer's rewrite
just **regresses** (downgrades a resolved epithet to `(unknown)`, re-attaches a referent)
— "review" becomes a worse re-generation. A **minimal-diff** review (splice in only an
`n. Name` override, re-run the check, discard a splice that breaks it) holds *mechanically*
but not on substance: the structure check guards structure, not interpretation, so a
spliced edit can still mis-name a tag and pass. With a reviewer weaker as a reader than the
31B generator (§6), such confident-but-wrong edits **outnumber** the genuine catches at the
cost of a second-model pass per scene: net-negative. The lesson: a
free generative layer's structure check **cannot stand in for** the interpretation review a
round-trippable layer (§6) gets; prefer one clean generation pass unless a reviewer at least
as strong a reader as the generator (or a human) is available.

**Narrow the resolution turn to enumeration, identity-first — it must not re-decide
WHO.** Given a second, open-ended chance to name each tag, the resolution re-decides
and *regresses* (an epithet of an already-named figure left un-named; a tag the
reading had resolved downgraded to `(unknown)`). So the turn is narrowed: "your
reading above already established WHO each tag is — keep those identifications, write
each as the MOST SPECIFIC identification the reading gives, in source spelling."
Identity-first means a figure the reading identifies by proper name gets that name
even when this scene's text has not uttered it (the reading's "a soul (specifically
Beatrice)" commits as `Beatrice`, not the in-text epithet `anima`); only a figure the
reading itself tracks by epithet alone (a beast, a simile figure, a generic) keeps
the source-text epithet. Anything less specific commits data *poorer* than the
reading it was built from, and the downstream registry has to go back to the prose to
recover what the pipeline had already resolved once. Two further choices keep the
turn honest. *Don't re-extract the reading* — replay it in the conversation as the
assistant's reasoning turn and point the prompt at it, rather than parsing its
per-tag lines back out: free-form prose has **no fixed resolution format**, so any
regex silently returns nothing on a format it didn't anticipate, losing the guard
with no error. *Don't ask the model for the surface form* — which words the text uses
for a tag is already in the markup (`number_scene`'s `meta` carries each tag's kind
and surface), so code pairs surface with identity mechanically (§12); the LLM's one
job is the identity.

**This project ships the uncheckable layer unproofread.** Promoting the interpretation to a
committed artifact (§2) makes it *amenable* to proofreading, but at canticle scale (100 cantos)
it is endless — so `reading.py` and the `tags.py` output ship as generated. The realized quality
gates are then exactly two: generation (CoT-on + the strong reader, §13) and the downstream
*structural* checks. Neither verifies WHO-correctness, so an interpretation error propagates to
the committed resolution unchecked — the accepted cost. When you forgo the human pass, say so
plainly and make generation quality carry the weight; do not let docs imply a safety net no one runs.

**A per-unit resolution pass cannot enforce cross-unit consistency — defer that to a registry
pass that sees every unit.** Resolving each scene in isolation keeps the pass simple and its
check local. Identity-first narrows the inconsistency a lot — a figure the reading knows by
proper name gets the same name in every scene — but where the *reading itself* tracks a figure
only by epithet, different scenes can still expose different epithets for one figure. Don't
fight this with per-unit prompt patches — the model can't see the other units, so it can't know
which surface is the canonical one. The clean fix is a *downstream pass with a roster* spanning
all units — a registry/reconciliation pass (built as `05-registry/`) that normalizes every
reference of one figure to a single canonical label. Keep the per-unit pass honest and local;
let the registry own the global invariant.

## 12. Fix in code what code can fix; retry only what needs the model.

A local model has persistent stylistic quirks — it varies a delimiter, wraps a token
in formatting, reaches for an equivalent-but-off notation. Sort every deviation into
two kinds:

- **Mechanically normalizable** — a cosmetic/format variant with one unambiguous
  canonical form (delimiter style, wrapping characters, equivalent notations). There
  is exactly one right answer and code can compute it.
- **Substantive** — a content error only the model can resolve (a wrong reference, a
  missing item, an invented one). Code can *detect* it but not *correct* it.

Don't spend prompt pressure or a retry trying to drill the model out of a mechanical
quirk — it is low-yield and steals attention from the real task. **Normalize the first
kind in code; route only the second kind back to the model** via the pinpointed retry
(§5). Keep the two layers distinct: the logic check should fire on substance, not on
cosmetics the code has already canonicalized.

**Worked example 1: `normalize_token_brackets` in `markup.py`.**
The LLM sometimes places a `[..]` bracket boundary inside a token — writing `[m]'` when
the tokenizer (`dante_corpus.tokenize`) treats `m'` as a single token. Drilling the model
out of this quirk via prompt pressure is low-yield; the canonical form (`[m']`) has one
unambiguous definition (bracket must span whole tokens). The function expands brackets
post-LLM to match token boundaries and rewrites the reply before it enters the validation
check and conversation history — so the model never sees the misaligned form in later turns.

**Worked example 2: `fix_elision` in `tags.py`.** The model sometimes writes a label
with an elidable determiner left un-elided before a vowel-initial word (`la altra`
where Italian requires `l'altra`). The repair is mechanical (drop the determiner's
final vowel, join with an apostrophe), so it runs in code on every parsed label —
asking the model to correct orthography in the prompt instead is exactly the
selective post-hoc instruction §8 warns about, and over-corrects.

**When you normalize, rewrite the conversation history with the cleaned text, not the
raw reply.** A multi-turn pass feeds each turn's output back as context (§2). If the raw
quirky form stays in the history, the model sees its own deviation in a prior turn and
perpetuates it — the quirk compounds across turns instead of being a one-off. Replacing
the assistant turn with the normalized form stops it at the source, so later turns only
ever see the canonical shape. Rewrite only the model's *own* replies this way; leave the
source material in the prompt intact.

## 13. Use the strongest reader; don't assume a task is fluency-bound.

Every pass here runs **Gemma 4 31B** (`31b-it-qat`) — the largest and strongest *reader*
(comprehension, coreference), if the slowest. It is the right model for every
coreference-bound pass: the reference markup (`markup.py`, round-trip-checked); the
interpretation-critical, unproofread reading (`reading.py`), CoT **on**, precision over
speed — generation is its only quality lever (§1/§11); and the tag resolution
(`tags.py`), where naming a tag is hard coreference.

Faster/smaller variants were tried for speed and dropped: even a layer that *looks*
fluency-bound ("just re-express an already-resolved reading") turned out judgment-bound —
re-expression still re-decides WHO and drifts — so the cheap model lost the job. The
lesson generalizes: **reader strength is not size-monotone, and "recast" is not
automatically a fluency-bound job — measure before assigning a weaker model to it.** Match
the model to the skill the pass actually needs (the §6 reviewer caveat is the same point).

## 14. To build a structured representation from interpretation-heavy text, formalize first.

When the end goal is a structured artifact — a knowledge graph, a relation store — over
figurative, allusive, pronoun-heavy text, do **not** extract entities and relations directly
from the surface. The literary surface (periphrasis, epithet, pro-drop, metaphor, embedded
speech) makes direct triple extraction bind relations to surface forms and misattribute: the
same figure splits across its epithets, a pro-drop subject floats free of its verb, an allegory
becomes a false literal edge ("a wolf blocks the road"). Worse, the interpretation error then
**fossilizes into the structure**, where it is far harder to see or fix than in prose.

Instead, insert a **literal intermediate** and separate *understanding* from *extraction*. One
interpretation pass recasts the text into plain propositions — who did what to whom, every
reference resolved — and the structured artifact is assembled **downstream of that, mechanically**.
This confines the hard, model-bound work (reading comprehension, coreference) to a single layer,
after which assembly is largely deterministic and checkable. It is §12 (code does what code can,
the model only what needs the model) and §2 (split the deliberation off into its own pass) scaled
from one call to the whole pipeline.

This is why the passes here climb a **ladder** rather than extracting in one shot —
`markup` (mark every mention) → `reading` (resolve them, in prose) → `tags` (each mention's
per-scene referent, machine-readable) → then downstream: a **registry pass** (`05-registry/`:
one canonical node per figure across the work, with node types and aliases — the alias
surfaces come from the markup itself, code-extracted), a **speech pass** (`06-speech/`: speaker
per quote span), and a **relations pass** (`07-relations/`: schema-shaped edges whose
subject/object roles cite tag numbers, with a frame marker for simile / prophecy / reported
speech), assembled into the graph by `08-kg/`. Each rung strips more literary surface and adds
more structure; the resolved referents plus the canonical roster are then the material a graph
is built from — by **code joining on tag numbers against a fixed schema**, not by another free
LLM pass. The completed ladder-to-graph is summarized in `README.md`. Two general corollaries:

- **Prefer a schema (a closed relation vocabulary) to open extraction** when the work is bounded
  and well-studied: the schema encodes domain knowledge and cuts noise, and it pairs naturally
  with formalize-first (you are normalizing *toward* known types, not discovering them).
- **Carry provenance and frame on every edge.** Anchor each relation to its source unit and the
  tag numbers that support it, and *reify* embedded assertions ("X said that Y did Z") rather than
  flattening them — the same tag-anchoring that makes §11 checkable makes the eventual graph
  auditable, and keeps a narrator's claim distinct from a diegetic fact.
- **Size the consolidation step from the FULL committed output, and split code-merge from the LLM
  residual before you measure.** The roster pass (§11) has a deterministic part (normalize + group by
  a fold key, canonical = most frequent spelling) and an LLM residual (typing each node; grouping the
  epithet variants code can't merge). A partial-run prototype here undercounted both by ~2×, and on
  the full output the recurring-epithet residual (~300/canticle) exceeded one batched LLM grouping
  call. When it does, prefer **flagged singletons (defer grouping)** over forcing the merge — the
  structure check guards structure, not correctness (§11), so an unverifiable merge is worse than an
  honest "not yet grouped". Typing stays tractable regardless (fixed-size batches over the node set).

## 15. Parallelizing a run: safety is a function of shared writable state; speedup, of the backend.

A canticle run is long, so the question of fanning it out (per canticle, per canto) across processes
comes up. Two independent questions:

**May you? — decided by shared writable state.**
- **No shared writable state → safe.** A pass whose outputs are per-unit files (`<canticle>/NN.txt`)
  and whose inputs are read-only committed files has nothing to race on; run the units concurrently.
  Most passes here are this kind.
- **A lock-free shared cache → must run as one process.** A pass that appends to a single unlocked
  file over *global* state corrupts it under concurrency and re-does the global work in each process
  — e.g. `05-registry`'s `types.txt` resume cache, written over the whole deduplicated node set. Run
  it as the one process its Makefile invokes.

Decide this per pass and state the verdict in **that pass's README** (the per-unit detail belongs
there, not in `PLAN.md`).

**Will it help? — decided by the backend (`-m`, the `model.mk` choice), not by correctness.** A
single local GPU serves one model, and a local backend (Ollama) serializes same-model requests by
default, so fanning out local clients only queues them — no speedup, and forcing concurrency
contends for VRAM. A *hosted* backend handles concurrency server-side, so the same fan-out gives a
real speedup there. Hence a parallel-safe pass is "parallel = pointless" on the local default yet
"parallel = N× faster" on the commented cloud backends — run the cloud and local models side by side
when it pays.

## 16. Reused code lives in the shared library `dante_analyze/`, not in another pass's script.

The pass scripts (`NN-name/*.py`) are entry points: each owns a run loop and writes its own output.
Logic that more than one pass needs belongs in the **package**, not in whichever script happened to
write it first. When a new pass needs a helper that already exists in another pass's script,
**promote it into `dante_analyze/`** and have both passes import it — never import one pass's
internals from another (the `NN-name/` dirs are not importable modules), and never copy-paste.

The package is already the single source of truth for the cross-pass primitives: the `load_*`
loaders, tag numbering (`number_scene`/`tag_positions`), label normalization (`norm_label`/
`fold_key`/`split_set`), and quote-span geometry. The name→registry-node join is the worked example:
`raw_to_canonical` started in `06-speech/speech.py`, and when `08-kg` (Step 4) needed the same join
it moved to `checkpoint.py` next to `load_registry`, with both passes importing it. One copy means
one place to fix when the registry format shifts. Re-export the promoted name from `__init__.py` so
passes import it from the top-level package.

---

**One-line summary:** local LLM = unreliable narrator. Keep each call small and
single-purpose, forbid CoT-in-output (split reasoning into its own plain-text
turn), verify every reply with code, normalize mechanical quirks in code (and rewrite
them out of the history) while pinpoint-retrying only substantive errors, accumulate
the good, guard runaway at the boundary, and never leak answers into the prompt.
