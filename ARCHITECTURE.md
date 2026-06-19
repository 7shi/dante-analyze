# Architecture

This repo runs local-LLM analysis passes over Dante's text and turns the result into
referent-resolved data and a knowledge graph. Local models are useful here, but they fail in
predictable ways: they loop, truncate, drift, invent formatting, and confidently misread
coreference. The architecture is built around one rule:

**The model proposes; code checks, normalizes, joins, and resumes.**

Read this before changing an existing pass or creating a new one.

## Core Principles

### Trust checks, not model confidence

Every pass should make the model emit something that code can validate. Prefer checks that need no
whitelist and lose no information:

- round-trip checks, where removing markup reproduces the source exactly;
- structural checks, where every expected id appears exactly once and no unknown id appears;
- geometry checks, where ranges fall inside exactly one known scene or quote span.

When a check cannot verify interpretation, say so plainly in the pass README. Do not imply a safety
net that is not actually run.

### Call the model only on the residual

Before calling the model, let code narrow each item to a candidate set. The size of that set decides
who resolves it:

- **deterministic cases** — where code can already decide the answer (zero candidates, or exactly
  one) — are resolved by code, with no model call;
- **the genuine residual** — where two or more candidates remain and only reading can choose — is the
  only thing sent to the model, and even then as a choice from the **closed candidate set**, not free
  generation.

The model is an **oracle for the residual**, not the default resolver. This keeps calls rare, makes
every answer a closed-set pick that code can check by membership, and records *which* path decided
each item (`source: code` | `llm` | `none`) so the split is measurable.

Examples from this repo:

- `06-speech` attributes a quote's speaker by code where the markup fixes it, and calls the model
  only for the ambiguous remainder.
- `12-addressee` builds the candidate pool from the scene's `present` cast minus the speaker, then
  branches on its size: 0 → `(none)`, 1 → that figure by code, ≥2 → the model picks one from the
  closed list.

Identity consolidation (`05-registry`, `10-topography`) applies the same rule to merging; see
*Separate deterministic merge from LLM residual*.

### Keep model jobs narrow

One call should have one job and one kind of check. Do not ask a local model to detect, resolve,
rewrite, extract, and structure in a single response.

Examples from this repo:

- `02-markup` marks references only; it does not resolve them.
- `03-reading` performs free interpretation.
- `04-tags` formalizes the reading into one identity per numbered tag.
- `05-registry` reconciles labels globally.
- `08-kg` assembles the graph by code only.
- `09-location` names each scene's current setting only.
- `10-topography` folds those settings into canonical regions only (the place analogue of
  `05-registry`).
- `11-presence` only labels each scene's already-resolved roster `present` / `mentioned` (the person
  analogue: code gathers the cast, the model classifies it).
- `14-lock` joins the five context-lock layers plus the KG into the per-scene lock by code only (the
  same code-only join as `08-kg`, one pass later in the ladder).

Split only as much as the current model tier needs. If a stronger model becomes available,
re-measure whether some scaffolding can collapse without losing accuracy.

### Work in small units

Process one scene per LLM call. A scene is short enough to keep generation stable and coherent; a
canto is the checkpoint unit. Whole-canto calls invite drift and runaway.

### No answer leakage

Prompts may include source text and general knowledge of the work. They must not include per-item
answers or worked examples drawn from the same item being processed. Examples should be schematic.

This matters especially for evaluation: text-derived examples from the canto teach the model the
answer and inflate apparent quality.

### Keep the project measurable

The committed outputs are a measurement of how far the automated local-LLM pipeline gets. Do not
hand-proofread generated outputs to make the data look better. Improve the method and regenerate
instead.

Residual errors in uncheckable interpretation are accepted data. Structural checks catch coverage,
format, and joins; they do not prove that every `WHO` decision is correct.

## LLM Call Design

### Chain of thought policy

Default: keep chain of thought out of checkable output.

CoT is slow and can collide with structured forms by looping or truncating the very text the checker
needs. Turn it on only when one of these is true:

- the output is uncheckable free prose, so hidden deliberation cannot corrupt a parser;
- the backend separates thinking from `resp.text`, and `call_llm` guards runaway length.

This is why interpretation-bound passes such as `03-reading`, `04-tags`, and `07-relations` can use
the strongest reader with thinking enabled, while simpler checked steps should not add thinking by
habit. `10-topography`'s same/new boundary is such a checked step: with CoT on, the local model
deliberated a short per-term label into runaway without improving the decision; CoT-off made the call
fast and decisive. Cost without benefit is the default outcome of adding CoT to a checked judgment.

Backend caveat: not every backend can turn thinking off cleanly. Hosted Gemma backends may leak
reasoning into the body when asked for CoT-off output. In that case, use the backend's separate
thinking channel if available and parse only the final text.

### Split deliberation from final output

If the model genuinely needs to reason, give that reasoning its own plain-text turn, then ask for the
checked output in a second turn in the same conversation.

Pattern:

1. Turn 1: free-form analysis only.
2. Turn 2: final plain or structured output.

`01-scenes` uses planning before structured scene output. `03-reading` promotes the reasoning turn
into a committed artifact. `04-tags` then replays that reading as the prior reasoning context before
emitting the checkable `n. Name` table.

Do not ask the model to mix hidden reasoning, commentary, and final schema in one response.

### Use the strongest reader for coreference

Many tasks that look fluency-bound are actually reading-bound. Re-expressing resolved material can
still re-decide who a pronoun or epithet names.

Use the strongest available reader for coreference-heavy passes. Smaller models are acceptable only
after measurement shows they preserve the same accuracy. A reviewer for interpretation must be at
least as strong a reader as the generator, or it will confidently regress correct readings.

### Guard runaway at the gateway

All ordinary LLM calls go through `dante_analyze.llm.call_llm`. It is the boundary that caps long
responses and detects repetition. On runaway, regenerate; runaway is stochastic, and a fresh draw
usually recovers.

`01-scenes` is the exception because it uses `llm7shi` structured output directly.

## Validation And Retry

### Accumulate good results

Never regenerate work that already passed. On retry:

- keep validated lines or ids;
- ask only for the failed items;
- identify failures precisely by id, source, and check message;
- retry inside the same conversation when context helps;
- fall back to a fresh per-item redo with nearby context for stubborn failures.

If something still cannot be validated, keep the safe subset and flag the unresolved item in the
output. Do not silently commit an unchecked guess.

### Normalize mechanical quirks in code

Sort deviations into two classes:

- mechanical: one unambiguous canonical form exists, and code can compute it;
- substantive: code can detect the problem, but only the model can decide the content.

Normalize mechanical quirks in code before validation and before the assistant reply is reused as
conversation history. Retry only substantive failures.

Worked examples:

- `normalize_token_brackets` expands brackets to whole token boundaries in `02-markup`.
- `fix_elision` repairs deterministic Italian elision labels in `04-tags`.
- label normalization helpers live in `dante_analyze`, not in prompts.

Do not spend prompt pressure on deterministic formatting. It distracts the model from the real task
and often over-corrects.

### Define placement rules structurally

Post-hoc instructions such as "after writing, verify placement" fire only when the model suspects a
problem. If placement matters, define the position structurally in the generation rule itself: for
example, before the entire preverbal clitic cluster, not merely "before the verb."

### Prefer stronger generation before review

A second-model review is not a default quality gate. In this project it often compensated for a weak
generator and introduced new interpretation errors.

Add review only when all of these hold:

- the generator is already strong enough for the task;
- the reviewer runs cold, seeing only source and draft;
- every correction is revalidated by the same logic check;
- known error classes are enumerated in the prompt;
- the reviewer is at least as strong as the generator for interpretation tasks.

For free-text interpretation, a review that rewrites the whole answer is especially risky because no
round-trip check can prove the rewrite preserved meaning.

## Interpretation To Structure

### Formalize before extracting

Do not extract a graph directly from Dante's surface text. The poem's periphrasis, pro-drop,
embedded speech, allegory, simile, and epithet chains make direct triples brittle: one figure splits
across names, a metaphor becomes a literal edge, and a reported claim becomes narrator fact.

Instead, use a ladder:

1. mark mentions;
2. interpret them in prose;
3. formalize each mention to an identity;
4. reconcile identities globally;
5. extract schema-shaped relations citing tag numbers;
6. assemble by code.

This keeps model-bound understanding in explicit layers and lets later passes join by deterministic
ids rather than reinterpret text.

### Anchor free interpretation to numbered tags

`03-reading` is uncheckable free prose. `04-tags` makes its coverage checkable by numbering every
marked mention in a scene and emitting exactly one `n. Name` line per tag.

The tag check proves only structure:

- every tag appears exactly once;
- no extra tags appear;
- no empty labels appear;
- pronoun tags do not merely echo the pronoun surface.

It does not prove that `Dante`, `Virgilio`, or `Beatrice` is the correct referent. That residual is
accepted unless a stronger method is added.

### Preserve identity-first labels

The tags pass must not re-decide `WHO`. It should enumerate the reading's identifications using the
most specific identity the reading establishes, in source spelling.

Rules:

- if the reading identifies a proper name, commit that name even if the scene text uses an epithet;
- if the reading only tracks an epithet, keep the source-text epithet;
- if the reading leaves the figure unidentified, use `(unknown)`;
- if one tag covers several figures, use a comma-separated set label.

Do not ask the model for surface forms. The markup already carries surfaces; code pairs surfaces
with identities.

### Defer global consistency to the registry

A per-scene pass cannot enforce cross-canto canonical labels. Do not patch prompts to make a local
unit solve a global problem it cannot see.

`05-registry` owns the global invariant: one canonical, source-spelled node per figure, with aliases,
sets, and node types. It sees the committed output as a whole and reconciles labels there.
`10-topography` is the place analogue: it folds `09-location`'s per-scene place surfaces into a
piecewise-constant region sequence. Because the journey is monotonic, region identity is positional,
so it walks the canticle in order and makes one narrow judgment per canto — a same/new boundary
against the current region — which keeps the sequence piecewise-constant by construction; code (not
the model) names each region from its members, the registry's deterministic-merge rule applied to
setting.

### Use schema and provenance

For bounded, well-studied work, prefer a closed schema to open extraction. `07-relations` uses a
closed predicate vocabulary and cites `[n]` tag numbers; `08-kg` joins those tags through
`04-tags` and `05-registry`. `11-presence` goes further: code gathers the closed roster (the scene's
already-resolved `05-registry` figures), so the model only labels each `present` / `mentioned` — a
closed-set classification that admits a total structural check (every roster figure labeled exactly
once, none outside it), instead of re-extracting identities the pipeline has already fixed.

Carry provenance on every structured record:

- canto and scene;
- source line range;
- tag numbers for relation ends;
- frame, such as literal, reported, prophecy, or simile;
- asserter where an embedded speaker owns the claim.

Frame prevents embedded assertions from flattening into narrator fact.

### Separate deterministic merge from LLM residual

When consolidating identities, first do what code can do: normalize labels, group by fold key, and
choose canonical spellings from observed forms. Send only the residual to the model. This is the
merge-specific case of *Call the model only on the residual*.

If a residual merge is too large or unverifiable, prefer flagged singletons over forced grouping.
An honest unresolved node is better than a confident but wrong merge that passes only a structural
check.

## Files, Checkpoints, And Runs

### Output files are checkpoints

A full run should skip any completed canto output, so interrupted runs resume cleanly and deliberate
edits survive. Provide a test mode such as `-c CANTO` to regenerate one unit.

When a pass is complete, its README should state what files are checkpoints and how to regenerate
them.

### Logs should supervise long runs

For long canticle runs:

- stream raw model output to stdout;
- send status and diagnostics to stderr;
- print separators for major steps;
- print a final verdict per unit;
- log the reason for every retry;
- flag unresolved items in the output itself.

The log should make it obvious which units passed, failed, retried, or were left partial.

### Parallelism depends on writable state and backend

Parallel safety is a correctness question:

- per-unit output files over read-only inputs are safe to run concurrently;
- shared lock-free writable caches are not safe and should run in one process.

Speedup is a backend question:

- a single local GPU or local Ollama backend often serializes same-model requests, so fan-out only
  queues work or contends for VRAM;
- hosted backends may handle concurrency server-side and benefit from fan-out.

State the parallel-safety verdict in the pass README.

## Shared Code

### Put reused helpers in `dante_analyze/`

Numbered pass scripts are entry points, not libraries. If more than one pass needs a helper, promote
it into `dante_analyze/` and import it from there.

Do not import another numbered pass's script. Do not copy helpers across passes.

Existing shared primitives include:

- project path constants;
- `call_llm`;
- checkpoint loaders;
- `number_scene` and tag-position helpers;
- label normalization: `norm_label`, `fold_key`, `split_set`;
- registry joins such as `raw_to_canonical`;
- the per-tag coreference overlay applied inside `load_tags` (`load_coref`, `04-tags/coref.txt`):
  identity corrections live at the single tag-read layer so every consumer sees one per-tag
  identity — `raw_to_canonical` is a global `fold_key` map and cannot route one surface to two
  nodes, so disambiguation must be in the label, not the join;
- quote-span geometry.

Re-export promoted public helpers from `dante_analyze/__init__.py` when other passes or users should
import them from the top-level package.

### Keep docs at the right level

Root docs describe cross-pass rules and current planning:

- `README.md`: what exists and how to use it;
- `PLAN.md`: possible next directions;
- `ARCHITECTURE.md`: durable engineering rules.

Per-pass READMEs describe that pass's purpose, inputs, outputs, checks, model choice, run commands,
parallel-safety status, and measured results.

## One-Line Summary

Keep each LLM call small and single-purpose; prevent answer leakage; split reasoning from checked
output; validate every response with code; normalize deterministic quirks in code; retry only
pinpointed substantive failures; checkpoint every unit; and assemble structured data by joining
stable ids rather than asking the model to reinterpret text.
