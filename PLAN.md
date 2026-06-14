# dante-analyze — KG layer: plan & status (2026-06)

> **▶ STATUS: the ladder scenes → markup → reading → tags is ✓ complete & committed; the registry
> (`05-registry/`, KG Step 1), the speech pass (`06-speech/`, KG Step 2), the relations pass
> (`07-relations/`, KG Step 3), and the KG assembly (`08-kg/`, KG Step 4) are all ✓ DONE & committed.
> **The KG ladder is complete** — `08-kg/{inferno,purgatorio,paradiso}/NN.json` (edges + speech
> edges per canto) + `08-kg/<canticle>.nodes.json` (node table) are committed; design in
> `08-kg/README.md`. Next = the deferred work (Digest edition; the pronoun-layer quality items) or a
> consumer of the graph (`dante-dravidian`).
>
> **Where to pick up (check this first):**
> - **All four KG steps are DONE** — the assembled graph is committed under `08-kg/`. There is no
>   open build step in this plan; see "Deferred" and "Digest edition" below for the remaining work.
>
> Full designs are in each subdir's `README.md` (or `PLAN.md` while a pass is under construction).
> Read `ARCHITECTURE.md` before building or changing any pass.**

`dante-analyze` turns the source cantos into referent-resolved structured data — the precursor to a
knowledge graph. It consumes the shared corpus (source lines, tokens, scene ranges, the quote-span
tree) from **`dante-corpus`** via its Python API, and runs local-LLM analysis passes on top. The
patterns every pass shares are written up once in **`ARCHITECTURE.md`**; all LLM calls go through
the single shared gateway `call_llm` (`dante_analyze/llm.py`). The speaker/edge data the KG produces
is intended to feed the translation context lock (`dante-dravidian`).

## Done — don't redo

- **The ladder** `02-markup` → `03-reading` → `04-tags` is complete and committed for all three
  canticles (100 cantos). Design detail lives in each subdir's `README.md` (e.g. `04-tags/README.md`)
  and in `ARCHITECTURE.md` (the formalize-first rationale is ARCH §14).
- **Registry library primitives**, verified across all 1,796 committed scenes with **0 tag-number
  desync** (`number_scene` / `tag_positions` / `load_tags` aligned):
  - `dante_analyze/labels.py` — `norm_label`, `fold_key`, `split_set`, `FIRST_PERSON_{STRONG,WEAK,PLURAL}`.
  - `dante_analyze/marks.py:tag_positions` — column-aware tag positions; mirrors `number_scene`'s
    non-nesting tokenization so tag numbers stay aligned (the 10 corpus-wide nested-brace lines,
    e.g. `{figliuol d'{Anchise}}`, are an accepted ≤1-column anomaly, flaggable by Step 2's
    round-trip assert).
  - `dante_analyze/quotespans.py` — `walk_spans`, `contains`, `own_region` over `QuoteSpan`
    `start_col`/`end_col`.
  - `_paths.py` `REGISTRY_DIR`/`SPEECH_DIR`; all re-exported from `__init__.py`.
- **`05-registry/measure.py`** — pure-code measurement report over the full 04-tags (writes nothing).
- **dante-corpus column extension** — `QuoteSpan.start_col`/`end_col` shipped and editable-installed.

## KG build steps

### Step 1 — registry build (`05-registry/registry.py`)  [DONE & committed]

One canonical, source-spelled node per figure across the work, with **node typing** (closed
vocabulary, LLM, cached in `types.txt`), **set** support, and code-extracted **alias surfaces**;
epithet grouping is skipped in v1 (**option A** — every non-name node flagged `grouped: no`).
`measure.py`, `registry.py`, the three `<canticle>.txt`, and `types.txt` are all built & committed.

**→ Design, sizing numbers, output format, the structural check, and the option-A rationale are in
`05-registry/README.md`.** `load_registry(canticle)` is in `checkpoint.py`.

### Step 2 — speaker per quote span (`06-speech/speech.py`, pure code)  [DONE & committed]

For every quote span, speaker = the unique canonical first-person referent in the span's own region,
joined onto the registry nodes; else `(unattributed)`. No LLM — the work is geometry plus a join.
Built & committed for all three canticles.

**→ Design, the per-canto algorithm, output format, the measured coverage, and the structural/
round-trip checks are in `06-speech/README.md`.** `load_speech(canticle, canto)` is in `checkpoint.py`.

### Step 3 — Relations pass (`07-relations/relations.py`)  [DONE & committed]

The KG's event edges (who-does-what-to-whom): one LLM pass per scene, bound to the reading like
`tags.py`, emitting `- [subj] predicate [obj] | frame: … | lines a-b` edges that cite the 04-tags
`[n]` (closed **31-predicate** vocabulary, four-point structural check, CoT on). `relations.py` + the
wiring (`RELATIONS_DIR`, `load_relations`, `cli.py` `relations show`, `Makefile`) are built and
verified end-to-end on Inferno canto 1.

**→ The full design — measure-first rationale, the line grammar, the four-point check, the `[n]`
join invariant, and the Step-4 assembly contract — is in `07-relations/README.md`.**

All 100 canto outputs are built and committed. The design, the four-point structural check, and the
Step-4 assembly contract are in `07-relations/README.md`.

### Step 4 — KG assembly (`08-kg/assembly.py`)  [DONE & committed]

Join the committed edges and speaker data into the graph. **Pure code** — every input is a committed
file read through the **`load_*` public API** (signatures in `dante_analyze/README.md`); no model is
involved. The upstream structural checks are what make this join total.

`08-kg/assembly.py` + the wiring (`KG_DIR`, `load_kg`, `load_kg_nodes`, `cli.py` `kg show`,
`Makefile`) are built, generation-run & committed for all three canticles: geometry checked with 0
failures across all 100 cantos (every edge in exactly one scene, every cited tag present), 18
unresolved edge ends total (all `(unknown)` labels). **→ The full design and the measured result are
in `08-kg/README.md`.** What follows is the original build spec.

Per canticle, per canto, over `load_relations(canticle, canto)`:
- **Resolve each end to a node.** An edge's `start..end` lies in exactly one scene (scenes partition
  the canto), so find that `(s, e)`, then map `subj`/`obj` through `load_tags(canticle, canto)[(s, e)]`
  → a name, and through `load_registry(canticle)` (`fold_key(name)` → canonical heading) → the
  registry **node**. Attach provenance (canticle / canto / scene / lines + the tag numbers) and the
  edge's `frame`.
- **Recover the asserter.** For `reported` / `prophecy` / `simile` edges, join the edge's line range
  to the speaker of the containing `06-speech` quote span (`load_speech`); `literal` edges are
  narrated and have no asserter. (Full contract: `07-relations/README.md` "Step-4 assembly contract".)
- **Merge the speech edges** (speaker → quote span) alongside the relation edges.

JSON is acceptable as the machine artifact here. Per the subdir convention, start a new numbered dir
(e.g. `08-kg/`) with a `PLAN.md` build spec, rewritten into `README.md` once built; add an
`assembly`/`kg` reader to `cli.py` and a loader to `checkpoint.py` if the artifact warrants one.

### Wiring (with Steps 1–2)

- Makefiles + `cli.py` entries (`registry show <canticle>`, `speech show <canticle> <canto>`).
  Registry-specific wiring is in `05-registry/README.md`; `06-speech/Makefile` is pure code (no `model.mk`).
- **Convention**: a pass under construction has a `PLAN.md` in its subdir (scope-narrowed build
  spec). Once built, the `PLAN.md` is **not renamed but rewritten into a `README.md`** — a different
  document: it drops the build-time scaffolding (remaining-work lists, "build X from this", step
  ordering) and becomes a purpose-and-design doc that **explains what the pass is for and quotes the
  pass's own committed output** to show the result (cf. `04-tags/README.md`, `06-speech/README.md`,
  `07-relations/README.md`). Make the new subdir `PLAN.md` in the build-spec style; rewrite it on
  completion.

### Verification

```bash
cd /home/7shi/repos/dante-analyze
uv run python -c "import dante_analyze; print('ok')"
uv run 05-registry/measure.py                  # regression: re-confirm the gate numbers
make -C 05-registry                            # Step 1: resume/finish typing + structural check
uv run dante-analyze registry show inferno
make -C 06-speech                              # Step 2: build speech + fail-loud structural check
uv run dante-analyze speech show inferno 1
# spot-check: every speech speaker is a registry node (the structural check enforces it)
uv run 07-relations/measure.py                 # Step 3: regression — re-confirm the 31-predicate gate
make -C 07-relations                           # Step 3: full generation run + per-scene structural check
uv run dante-analyze relations show inferno 1
make -C 08-kg                                  # Step 4: assemble the graph + geometry check (0 failures)
uv run dante-analyze kg show inferno 1
```

## Pipeline (data flow)

```
  dante-corpus (shared inputs, via the dante_corpus API — no LLM):
     source cantos ─→ canto.lines() / Line.tokens / canto.quotes()                  [done]

  dante-analyze ladder (committed):
     01-scenes/<c>/NN.json → 02-markup → 03-reading → 04-tags/<c>/NN.txt             [done]
        (markup round-trip-checked; reading free prose, no check; tags identity-first, structure-checked)
     05-registry/measure.py → stdout report (registry sizing + gates, pure code)     [done]

  KG build (complete — this plan):
     05-registry/registry.py  → 05-registry/<c>.txt      canonical nodes + types      [Step 1 ✓]
     06-speech/speech.py      → 06-speech/<c>/NN.txt      speaker per quote span       [Step 2 ✓]
     07-relations/measure.py  → stdout report (CLOSED_VOCAB probe, pure code)          [Step 3 ✓]
     07-relations/relations.py → 07-relations/<c>/NN.txt  schema edges per scene       [Step 3 ✓]
     08-kg/assembly.py        → 08-kg/<c>/NN.json + <c>.nodes.json  the joined graph   [Step 4 ✓]
```

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
- **The ultimate aim is a knowledge graph** of the poem (entities + who-does-what + relations).
  03-reading/04-tags produce the referent-resolved material; the registry, speech edges, and
  relations pass turn that into nodes and edges by code joining on tag numbers (ARCH §14).
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
not a translation product. Deferred until after the KG.

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
