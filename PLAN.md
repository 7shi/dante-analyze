# dante-analyze — remaining work: plan & status (2026-06)

> **▶ STATUS: the ladder (`02-markup → 03-reading → 04-tags`) and the full KG (Steps 1–4,
> `05-registry → 08-kg`) are ✓ complete & committed for all three canticles (100 cantos).**
> The KG overview now lives in `README.md`; per-pass design and measured results are in each
> subdir's `README.md`. Regenerate the graph with `make -C 08-kg`.
>
> **There is no open build step in this plan.** The remaining work is a choice of direction
> (no default — decide before starting):
>   1. **Digest edition** (`## Digest edition` below) — the next analyze-side deliverable; its
>      precondition ("after the KG") is now met. A new prose-generation pass over `03-reading/`.
>   2. **Deferred quality work** (`## Deferred` below) — pronoun-layer marking quality + its logic
>      checks (both gated on a stronger model / a reliable pronoun lexicon), and diff-only storage.
>   3. **Graph consumer** — feed the speaker/edge data to the translation context lock
>      (`dante-dravidian`), the KG's original purpose. Out of this repo, but the natural next use.
>
> **Read `ARCHITECTURE.md` before building or changing any pass.**

`dante-analyze` turns the source cantos into referent-resolved structured data and a knowledge graph
of the poem. It consumes the shared corpus (source lines, tokens, scene ranges, the quote-span tree)
from **`dante-corpus`** via its Python API, and runs local-LLM analysis passes on top. The patterns
every pass shares are written up once in **`ARCHITECTURE.md`**; all LLM calls go through the single
shared gateway `call_llm` (`dante_analyze/llm.py`). The completed work — the ladder and the KG — is
summarized in `README.md`; this document tracks only what remains.

## Conventions for new work

- **Convention**: a pass under construction has a `PLAN.md` in its subdir (scope-narrowed build
  spec). Once built, the `PLAN.md` is **not renamed but rewritten into a `README.md`** — a different
  document: it drops the build-time scaffolding (remaining-work lists, "build X from this", step
  ordering) and becomes a purpose-and-design doc that **explains what the pass is for and quotes the
  pass's own committed output** to show the result (cf. `04-tags/README.md`, `06-speech/README.md`,
  `07-relations/README.md`). Make the new subdir `PLAN.md` in the build-spec style; rewrite it on
  completion.

## Decisions to keep

- **Source-spelling names** everywhere (`Virgilio`, not "Virgil"), **identity-first**: the committed
  label is the most specific identification the reading establishes, never a scene-local epithet for
  a figure the reading already names (ARCH §11).
- **No answer leakage**: prompts carry source + general knowledge, never per-item answers nor
  text-derived worked examples — `ARCHITECTURE.md` §8.
- **CoT policy**: plain text + per-scene + logic-checked retry on the **checkable** passes; CoT is
  **ON** for the 31B interpretation-bound passes — `reading.py` (uncheckable free prose), `tags.py`
  (judgment-bound coreference) and `relations.py` (judgment-bound edge extraction), the last two
  structure-checked under §1's two safety conditions. The general rule is ARCH §1.
- **Over-marking is acceptable** for the name layer: the downstream consumer tolerates false
  positives; missing a reference is more harmful.
- **Orthography is code's job** (ARCH §12): mechanical quirks (`fix_elision`,
  `normalize_token_brackets`, `unbrace`) are normalized in code and rewritten into the conversation
  history — never requested of the model in the prompt.
- **All LLM calls go through one shared gateway** (`call_llm` in `dante_analyze/llm.py`); `llm7shi`
  is therefore a normal runtime dependency of this package (01-scenes is the one exception — it uses
  llm7shi's `generate_with_schema` structured-output path, not the plaintext `call_llm` gateway).
- **Reused code → shared library**: promote a helper reused across passes into `dante_analyze/`;
  don't import across passes or copy, and document it in `ARCHITECTURE.md`.
- **The ultimate aim is a knowledge graph** of the poem (entities + who-does-what + relations) —
  now built (`05-registry → 08-kg`, see `README.md`); its speaker/edge data is intended to feed the
  translation context lock (`dante-dravidian`).
- **The pipeline is an experiment: how far can a LOCAL LLM analyze the work.** The deliverables
  double as a measurement of capability, so the success criterion is **confirming the current
  accuracy of the automated pipeline, not perfecting the output**. Hence **no hand-proofreading**
  (it would mask the model's true accuracy); 03-reading/04-tags ship as generated and residual errors
  are accepted data. Improving accuracy = changing the *method*, never patching by hand. (Mechanism
  — why the structural checks don't catch WHO-errors — is ARCH §11.)
- **Reading vs. tags = free interpretation vs. tag-anchored formalization** — two passes, two kinds
  of work; don't fold them back together. The reading decides WHO once; tags enumerates it under a
  structural check. Numbered-tag anchoring keeps the formalized half verifiable (ARCH §11).

## Deferred

- **Pronoun-layer marking quality** — local models still make errors on Inferno 1: spurious/misplaced
  `[+pron]` supply (needs clause parsing), non-pronoun bracketed, wrong pronoun category/form. The
  hard classes need a stronger model; the partly-checkable classes are deferred pending a reliable
  pronoun lexicon.
- **Remaining pronoun-layer logic checks** — misplaced-supply detection (`[+..]` not immediately
  before a verb); nominative-only supplied-pronoun check. Both need a pronoun lexicon.
- **Diff-only storage** — store only additions vs. the source token list.

## Digest edition (future)

Goal: a retelling of each canticle that is **more detailed than a bare plot summary but lighter than
a full line-by-line translation**, at a granularity where the plot can be read as a story. It is an
**analyze-side deliverable** — derived from `03-reading/` (which already resolves WHO per scene) —
not a translation product.

- **Density**: **one to two sentences per scene** — enough to convey who acts and what happens, while
  skipping the dense doctrinal and prosodic detail of the full text.
- **Unit**: scenes are **grouped into paragraphs**, several scenes per paragraph, roughly **3–5
  paragraphs per canto**. A scene is *not* its own paragraph; the per-scene sentences flow together
  into continuous narrative prose.
- **Source of truth**: `03-reading/` carries the referent-resolved prose; the source text and corpus
  scene split (`dante-corpus`) anchor it to the canonical text.
- **Form**: prose paragraphs under `## Canto N` headings. It deliberately breaks line fidelity, so it
  is its own prose-generation pass with its own check — **narrative coherence + factual accuracy** —
  not a coverage/word-table check. Keep it cleanly separate from the translation pipeline.
- **Inputs**: `03-reading/<canticle>/NN.txt` (primary), `01-scenes/<canticle>/NN.json` (paragraph
  grouping), `01-scenes/<canticle>.md` (incidental, not authoritative). A vetted translation, if one
  later exists, could enrich it but is not a dependency.
