# Local-LLM scripting patterns (read before building a new pass)

The analysis scripts here (`01-scenes/scenes.py`, `02-markup/markup.py`, `03-reading/reading.py`, `04-bullets/bullets.py`, `05-tags/tags.py`) drive a
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

**The runaway danger is CoT colliding with *structured/checkable* output** — the
model loops or truncates the very form your check reads. So the rule is firmest where
output is checkable. On a layer whose output is **uncheckable free prose with no
structured form** (e.g. `reading.py`, §11), CoT has nothing to corrupt: the thinking
stays internal and the saved text is plain prose. There, when the layer is also
*precision-critical and not machine-gated* — and especially when it is not proofread either, so
generation is its only quality lever (§11) — it is worth turning CoT **on** (and using a larger
model), trading speed for interpretation quality.

The collision is what's dangerous, not the deliberation — so two conditions defuse it
even on a *checked* pass, and where they hold, CoT can be on there too. (1) **The
backend routes thinking to a separate channel** (Ollama `think=True`; see the caveat
below for backends that don't), so the deliberation never physically intermixes with
the checkable text — `resp.text` stays clean for the check to read. (2) **A runaway
guard caps generation** (`call_llm`'s length limit), so a looping CoT is cut
off rather than eating the output. With both in place, CoT-on pays off on a pass whose
work is judgment-bound even though its *form* is checked — which is why `bullets.py`
(bullets, coverage-checked) and `tags.py` (resolution, structure-checked) both run CoT
on: naming WHO is hard coreference, and the guard + separate channel cover the risk.
The firm "CoT off" rule is for the case those conditions *don't* hold — a backend that
lands thinking in the answer channel, or a pass with no runaway guard. Default off;
turn it on deliberately, and only when both conditions hold.

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

This is the shape of `scenes.py` (planning turn → structured turn) and of the
`markup.py` self-review (critique turn → corrected marking).

**When the deliberation prose is itself a deliverable, promote it to its own script
and committed artifact.** The reasoning turn need not stay throwaway scratch context.
`reading.py` is exactly bullets.py's old Turn 1 (a free English reading of the scene)
split off into a committed file; `bullets.py` then **replays that
reading as the assistant's reasoning turn** before its two checkable turns (bullets,
resolution). Same split-the-turns shape, but the deliberation is now a committed,
inspectable, reusable output in its own right — amenable to proofreading if one chooses,
though this project ships it as generated (§11).

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

## 6. Independent review runs in a fresh session, and can only refine faithfulness.

A self-review must **not inherit the generation conversation** (that biases it
toward defending its own draft). Start a new session showing *source + draft* cold.
Re-validate every correction with the **same logic check** as the original pass, so
review can only improve: a "correction" that fails the check is discarded and the
draft kept. (And keep its examples schematic — see §8.)

**The logic check guards faithfulness, not marking quality.** A round-trip check
only proves that marks were added/removed correctly — it cannot tell whether the
*right* things were marked. The review can still wrongly remove valid marks and
wrongly add invalid ones; the net should be positive, but errors in both directions
are possible. Monitor the review's changes (diff the mark and review checkpoints)
when tuning.

**Use a different model for review.** Generation and critique are different skills;
the model that is best at marking from scratch is often not best at catching its own
errors. A two-model pipeline — one model for the mark phase, another for review —
is more complementary than using the same model twice.

**But ask first whether a stronger single generation pass would obviate the review.**
`markup.py` was originally built early: a CoT-**off** Gemma draft + Qwen round-trip review
(§1's default-off rule, before the CoT-on practice on the 03-reading/04-bullets/tags layers
was established). The review may have been compensating for a deliberately under-powered
generator rather than catching errors intrinsic to the task. This was addressed in the
refactor: `markup.py` now runs the **31B reader with CoT on** as a single pass (both
pronoun and name layers in one call), with no second-model review — the round-trip check
polices every line, and a post-LLM token-boundary normalization step (`normalize_token_brackets`)
canonicalizes bracket edges before the check runs (§12). The lesson is ordering — **spend
on generation first (model size, CoT, §1/§13), and add a review pass only for what a strong
single pass still misses**, not as a reflex.

**But the reviewer must be at least as strong a *reader* as the generator.** The win
above is for a *checkable* task (round-trip marking): there the reviewer only has to
spot mechanical add/remove errors, and on this project Qwen 3.6 (`-rm`) complements
Gemma 4 (`-m`) well. It does **not** transfer to an *interpretation* task. The two
local models are not equal readers: Gemma 4 is the stronger at reading
comprehension / coreference (and within Gemma the larger 31B is the stronger reader — §13),
while **Qwen 3.6, though tidy at structured, rule-shaped
critique, is markedly weaker at reading comprehension** — so pointing it at the
interpretation layer's review (the 04-bullets/tags resolution) made it confidently rewrite
*correct* readings into wrong ones (§11). Match the review model to the skill the review actually needs: mechanical
critique can go to a complementary smaller/faster model, but interpretation critique
needs a reader at least as capable as the generator (the same model, a larger one, or
a human) — a weaker reader as reviewer is worse than no review.

**Enumerate known error classes in the review prompt.** A generic "find mistakes"
instruction yields vague critique. A `Watch especially for:` list that names the
specific error types observed in earlier runs focuses the model's attention and
significantly improves recall. Add to the list as new error classes are discovered.

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
one unit and only writes with `--save`. Committed outputs are hand/LLM-editable;
gitignored outputs are regenerable artifacts.

## 10. Log a long local run so progress is legible.

A canticle run is long; the log is how you supervise it. Conventions used here:

- Stream the model's raw output to **stdout**; status/diagnostics to **stderr**.
- Print a **step separator** (e.g. `--- pronoun mark ---`, `--- name review ---`,
  `--- per-line redo ---`) before each step.
- Print a **final verdict per unit** — `OK — all N validated` vs
  `NOT resolved — lines [...] still failing` — so resolved vs. abandoned is
  readable from the log alone (don't make the reader infer it).
- On retry, log *why* (the failing check's message), not just a count.
- Flag unresolved items in the final output itself.

## 11. Anchor a free generative layer to numbered tags so coverage stays checkable.

Some passes can't round-trip: recasting a scene as a free English "who did what"
bullet list and resolving each reference to a person is an *interpretation*, which no
logic check can verify (is `io` here Dante or the enclosing speaker?). This work is
**split across scripts at the checkable seams**. `reading.py` does the pure
interpretation as free prose — uncheckable, so it carries NO machine check and is a
committed artifact that ships **as generated** (this project does not proofread it — see
the note below; its only quality lever is generation, CoT-on + the strong reader).
`bullets.py` and `tags.py` then re-ground that reading to the marks. Do not give up on a
check on the checkable half; **anchor the formalized output to the marks**. Number every mark
in the unit (`[1:io]`, `{4:Virgilio}`, deterministically); `bullets.py`'s bullets **cite tags
by number** (`[n]`) and `tags.py` emits one numbered `n. Name` line per tag. Then a check
stands even though the prose is free: every tag cited by at least one bullet and named exactly
once (nothing dropped), no tag referenced outside the set (nothing invented). A cheap lexical
guard also catches a *non*-resolution — a pronoun tag whose `n. Name` line merely echoes the
pronoun surface (`1. io`) rather than naming a person. This is the round-trip
principle (§1) carried to a layer that can't round-trip — the check guards *coverage and
structure*; the interpretation it cannot verify (is `io` Dante or the speaker?) is **left
unverified** and shipped, an accepted residual (this project does not proofread; see below).

A §6 review on a free-text layer is hard to make pay, so **none of the interpretation
passes carries one**: `bullets.py` (bullets, coverage-checked) and `tags.py` (resolution,
structure-checked) both ship their single generation pass, as does the unchecked
`reading.py`. The reason a second-model review does not help here is structural. A full
re-emission has no round-trip constraint, so the reviewer's rewrite just **regresses** —
on the bullets it reintroduces pronouns; on the resolution it downgrades a resolved epithet
to `(unknown)` — and "review" becomes a worse re-generation. A **minimal-diff** review
(emit only an `n. Name` resolution override or an `N: corrected bullet`, splice it in
verbatim, re-run the check, discard a splice that breaks it) holds *mechanically* but not
on substance: the coverage check guards only **coverage**, the structure check only
**structure**, neither guards the **interpretation** — so a spliced edit can still
reintroduce a pronoun, drop or duplicate content, or mis-name a tag and pass the check.
With a reviewer weaker as a *reader* than the 31B generator (the only local option here —
§6), such confident-but-wrong edits **outnumber** the genuine catches, at the cost of a
full second-model pass per scene: net-negative. The lesson: a free generative layer's
coverage/structure check **cannot stand in for** the interpretation review a
round-trippable layer (§6) gets; on such a layer, prefer one clean generation pass over a
local-model review whose edits the check cannot police — unless a reviewer at least as
strong a reader as the generator is available. Human proofreading is the other way to close
the gap, but it is a *choice*; this project declines it at scale (next note), and a flawed
auto-review is worse than shipping the clean pass unreviewed.

The tag also **separates an authoritative channel from a non-authoritative one** — and here
that separation is two *passes*, not two turns. The bullet's surface name (`bullets.py`) is a
working label and may anglicize ("Virgil") — harmless, because the downstream data comes from
the tag, not the prose. The authoritative numbered `n. Name` resolution (`tags.py`, line n =
tag [n]) is held to the source spelling (`Virgilio`). So you can let the bullet pass write
English freely (better than forcing Italian on a model whose pretraining is
English-heavy, and without per-name spelling instructions that would pull attention off the
interpretation) while the committed data — a separate pass — stays in source form.
The two-pass split was *also* expected to let each channel run a cheaper model on the easier
job (a fast MoE on the "just fluency" bullets, the reader only on the resolution), but that
did not survive evaluation (§13): naming WHO in the bullets turned out to need the same
coreference judgment as the resolution, so both passes run the 31B reader. The payoff that
remains is structural — the reading-direct binding (below) and the two distinct checks
(coverage vs. structure) — not a per-pass model saving.

**Narrow the resolution pass to spelling, so it can't re-decide WHO — and bind it to the
reading directly, not to the bullets.** Given a second, open-ended chance to name each tag, the
resolution re-decided and *regressed* (left an epithet of an already-named figure un-named;
downgraded a tag the reading had resolved to `(unknown)`). The fix is to **narrow the resolution
to spelling only**: "your reading above already established WHO each tag is — keep those
identifications, just rewrite each in source spelling." Two further choices keep it honest.
*Don't re-extract the reading* — point the prompt at the reading already replayed in the
conversation rather than parsing its per-tag lines back out: a parser duplicates what is already
in context, and free-form prose has **no fixed resolution format**, so any regex
silently returns nothing on a format it didn't anticipate, losing the guard with no error.
*Don't feed it the bullets either* — `tags.py` is a separate pass that sees only the reading,
not `bullets.py`'s bullets. WHO drift used to flow bullets → resolution (a fast model re-attached
a tag in the bullet prose, the table followed); resolving straight from the reading
removes that path, so the faster bullet model's drift can't poison the authoritative tags. The
reading stays the single source of truth for WHO — itself unverified (not proofread), so any
residual mis-spelling is an accepted residual, not something a spelling-fragile automated check
should chase.

**This project ships the uncheckable layer unproofread.** Promoting the interpretation to a
committed artifact (§2) makes it *amenable* to proofreading, but proofreading is a choice, and
at canticle scale (100 cantos) it is endless — so here `reading.py` (and the `bullets.py` /
`tags.py` outputs) ship as generated. The realized quality gates are then exactly two: the
generation itself (CoT-on + the strong reader, §13) and the downstream *structural* checks
(coverage, structure). Neither verifies WHO-correctness, so an interpretation error in the
reading propagates to both formal outputs unchecked — the accepted cost of not proofreading.
When you forgo the human pass on an uncheckable layer, say so plainly and make generation
quality carry the weight; do not let docs keep implying a proofreading safety net that no one runs.

**A per-unit resolution pass cannot enforce cross-unit consistency — defer that to a registry
pass that sees every unit.** Resolving each scene in isolation keeps the pass simple and its
check local, but it means a label is only as canonical as what that scene exposes: a figure with
a proper name elsewhere, appearing in this scene only by pronoun and an in-text epithet, gets the
epithet here and the proper name there (Virgil → `Poeta` in the scene where he says only "Poeta
fui", `Virgilio` in the scene that names him). Don't fight this with per-unit prompt patches — the
model can't see the other units, so it can't know which surface is the canonical one. The clean
fix is a *downstream pass with a roster* spanning all units — a registry/reconciliation pass
(to be built downstream) that normalizes every reference of one figure to a single canonical
label. Keep the per-unit pass honest and local; let the registry own the global invariant.

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

**A concrete example of code normalization: `normalize_token_brackets` in `markup.py`.**
The LLM sometimes places a `[..]` bracket boundary inside a token — writing `[m]'` when
the tokenizer (`dante_corpus.tokenize`) treats `m'` as a single token. Drilling the model
out of this quirk via prompt pressure is low-yield; the canonical form (`[m']`) has one
unambiguous definition (bracket must span whole tokens). The function expands brackets
post-LLM to match token boundaries and rewrites the reply before it enters the validation
check and conversation history — so the model never sees the misaligned form in later turns.

**When you normalize, rewrite the conversation history with the cleaned text, not the
raw reply.** A multi-turn pass feeds each turn's output back as context (§2). If the raw
quirky form stays in the history, the model sees its own deviation in a prior turn and
perpetuates it — the quirk compounds across turns instead of being a one-off. Replacing
the assistant turn with the normalized form stops it at the source, so later turns only
ever see the canonical shape. Rewrite only the model's *own* replies this way; leave the
source material in the prompt intact.

## 13. Gemma 4 by size/variant (which model for which pass).

The passes here run several Gemma 4 sizes, chosen per job. The tendencies observed on
this project (Italian verse, coreference-heavy) — a reference, not a benchmark:

| Size / variant | Character | Best for |
| --- | --- | --- |
| **31B** (`31b-it-qat`) | Largest; strongest *reader* (comprehension, coreference). Slowest. | Every coreference-bound pass here: the interpretation-critical, unproofread reading (`reading.py`), CoT **on**, precision over speed — generation is its only quality lever (§1/§11); the bullet recast (`bullets.py`), where even "just re-express the reading" needs WHO judgment and pronoun control; and the tag resolution (`tags.py`), where naming a tag is hard coreference. |
| **26B MoE** (`26b`, faster `26b-a4b-it-qat` ≈4B active) | Fluent prose and **~2× the 12B's speed** (few active params), but weaker *judgment* on hard coreference (drifts WHO — re-attaches a referent, swaps a person for an abstraction) and more surface noise (typos, the odd hallucination). | A pass whose check *catches* judgment slips (round-trip markup was an early use-case; now markup runs 31B). Tried on the NON-authoritative bullet recast (`bullets.py`) for speed, but dropped: even re-expressing an already-resolved reading, it drifted WHO and avoided pronouns into noun-spam, so `bullets.py` runs the reader too. |
| **12B dense** (`12b-it-qat`) | Cleaner, more consistent, tighter WHO fidelity in limited sampling (possibly luck), but weaker *prose* (garbles English on hard passages). Slower per token than the 26B MoE despite fewer total params. | A fallback when the 26B MoE's drift/noise outweighs its fluency — but don't read one good sample as decisive. |

**MoE vs. dense, the rule of thumb.** Per *parameter / memory*, MoE is unfavorable (a 12B
*dense* ≈ the 26B *MoE* in quality — roughly the geometric mean of active×total params);
per *FLOP / compute*, MoE is favorable (the 26B MoE runs ~2× the 12B dense). Pick by which
is binding for the pass: quality-per-memory, or speed.

**Reader strength is not size-monotone across the lineup, and the reviewer caveat (§6)
applies within Gemma too.** Match the model to the skill the pass needs: a *reader* (31B)
for interpretation, a *fast fluent writer* (26B MoE) for fluency-bound recast, the *dense*
one when consistency matters more than fluency. A bigger MoE is not a strictly better reader
than a smaller dense model. A single scene's formalization is split into two passes (§11) —
the "who did what" bullets and the source-spelling tag resolution — but the hope of also
making them *two models* (fast MoE on the bullets, reader on the resolution) did not hold:
the bullets looked like fluency work but were judgment-bound (re-expressing the reading still
re-decides WHO and reaches for/avoids pronouns wrong), so both passes run the 31B reader. The
lesson cuts against the obvious read of this section: "recast" is not automatically a
fluency-bound job — measure before assigning the cheap model to it.

**Off-lineup: Qwen 3.6 (35B-A3B) as a generator — tried, not adopted.** Tested on the
combined bullets before the 04-bullets/resolution split (§11), its WHO *judgment* was on par with
the 26B MoE (it even held a hard referent the 26B drifted on), but it failed the
source-spelling job — now `tags.py`'s: it largely ignored the source-spelling instruction (left
labels in English, and spelled the same figure inconsistently across scenes), emitted one
scene's bullets in untranslated source language, and slipped hedging meta-notes into the
resolution table. That resolution is the committed *data*, so an instruction-follower that
won't hold source spelling is worse there than a weaker reader that does — consistent with
§6 (Qwen is tidy at rule-shaped structure but a weaker reader/instruction-follower on this
interpretive work). Generation stays on Gemma; Qwen's role here remains the round-trip
review (§6), not free-text generation.

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
`markup` (mark every mention) → `reading` (resolve them, in prose) → `bullets` (formalized
"who did what", proto-relations citing tags) → `tags` (each mention's per-scene referent) → a
**downstream registry pass** (one canonical node per figure across the work; to be built
downstream). Each rung strips more literary surface and adds
more structure; the resolved propositions plus the canonical roster are then the material a graph
is built from — by **code joining on tag numbers against a fixed schema**, not by another free
LLM pass. Two general corollaries:

- **Prefer a schema (a closed relation vocabulary) to open extraction** when the work is bounded
  and well-studied: the schema encodes domain knowledge and cuts noise, and it pairs naturally
  with formalize-first (you are normalizing *toward* known types, not discovering them).
- **Carry provenance and frame on every edge.** Anchor each relation to its source unit and the
  tag numbers that support it, and *reify* embedded assertions ("X said that Y did Z") rather than
  flattening them — the same tag-anchoring that makes §11 checkable makes the eventual graph
  auditable, and keeps a narrator's claim distinct from a diegetic fact.

---

**One-line summary:** local LLM = unreliable narrator. Keep each call small and
single-purpose, forbid CoT-in-output (split reasoning into its own plain-text
turn), verify every reply with code, normalize mechanical quirks in code (and rewrite
them out of the history) while pinpoint-retrying only substantive errors, accumulate
the good, guard runaway at the boundary, and never leak answers into the prompt.
