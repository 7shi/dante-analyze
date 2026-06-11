# dante-analyze — analysis layer: plan & status (2026-06)

> **▶ STATUS: markup refactor done — pipeline regeneration pending**
>
> 1. ✓ **Refactor `02-markup/markup.py`** — replaced the 4-step + Qwen-review pipeline with a
>    **single pass** using `gemma4:31b-it-qat` + CoT on. Output: `NN.txt` (committed).
> 2. **Regenerate the full pipeline** (markup → reading → bullets → tags). Address Deferred issues.
> 3. **Integrate tags into markup** — after new `05-tags/` is produced, incorporate the resolved
>    tag names back into the committed markup output. Naming convention TBD.
> 4. **Initial commit** — `git init` → `git add -A` → initial commit → create GitHub remote
>    → `git push`. Once this repo is published, `dante-dravidian` can also be pushed.

### Sanity check (run before committing)

```bash
cd /home/7shi/repos/dante-analyze
uv run python -c "import dante_analyze; print('ok')"
uv run dante-analyze tags show inferno 1
uv run 05-tags/verify_tags.py inferno purgatorio paradiso   # known residual: 1 item (purgatorio 08 64-81)
```

`dante-analyze` turns the source cantos into referent-resolved structured data (the
precursor to a knowledge graph). It consumes the shared corpus — source lines, tokens,
scene ranges, and the quote-span tree — from **`dante-corpus`** via its Python API, and
runs the LLM analysis passes on top. Every pass drives a **local LLM**; the patterns they
share are written up once in **`ARCHITECTURE.md`** — read that before building or changing
a pass here.

The pass scripts (`02-markup/markup.py`, `03-reading/reading.py`, `04-bullets/bullets.py`,
`05-tags/tags.py`, `05-tags/verify_tags.py`) live in their pipeline subdirectory and import the
shared library package `dante_analyze/`. All LLM calls go
through the single shared gateway `call_llm` (from `dante_analyze/llm.py`).

## ▶ Now (keep this section first; record where things stand)

- **Upstream pipeline needs regeneration.** `02-markup/markup.py` has been refactored (single
  pass, `gemma4:31b-it-qat` + CoT on, output `NN.txt`), but the markup files have not yet been
  regenerated; `03-reading/`, `04-bullets/`, `05-tags/` remain committed from the prior run and
  are not yet consistent with a fresh markup pass. The full pipeline must be re-run before this
  repo is committed. See Active work 0. The pipeline was previously complete for all cantos
  (Inferno 1–34, Purgatorio 1–33, Paradiso 1–33), fully automated, NO hand-proofreading
  (rationale: ARCH §11 + "Decisions to keep"). `05-tags/verify_tags.py` is the standing
  post-run check.

- **Known limit (cross-scene, NOT tags' job): per-scene `tags.py` can't hold one label per
  recurring figure.** Where a figure's proper name isn't braced in a scene, the per-scene pass
  takes that scene's epithet — Virgil → `Poeta` in 67-75 (only `[+io]` + "Poeta fui"), `Virgilio`
  elsewhere. This is by design (ARCH §11: per-unit local, the global invariant deferred to a
  registry). NOTE: the `reading.py` prose **already resolves the canonical identity** here (its tag
  resolutions say "Virgil", not "Poeta") — so cross-scene canonicalization is a downstream
  *reconciliation* of two existing resolutions (reading's identity + tags' source spelling), not new
  resolution. See Active work 1.

## Active work

0. **Pipeline regeneration** [do before initial commit].
   - Re-run `02-markup/markup.py inferno purgatorio paradiso`.
   - Re-run `03-reading/reading.py`, `04-bullets/bullets.py`, `05-tags/tags.py` on the new markup output.
   - Incorporate the resolved tag names from the new `05-tags/` back into the committed markup
     output. **Naming convention TBD — decide first.**
   - Run `05-tags/verify_tags.py` and confirm elision count = 0 and known residual (purgatorio 08
     scene 64-81) is resolved or still accepted.
   - Update `ARCHITECTURE.md` for any changes confirmed during regeneration.

1. **Downstream layer — reconciliation + edge derivation** [NEXT — the all-canto run is done, so
   this is now designable from the committed outputs / measured residuals; not yet started].
   With referents now resolved per scene (`05-tags/`) and the canonical identity already carried in the
   reading, the downstream is not interpretation but a lean, mostly-mechanical layer:
   - **Entity reconciliation (the node table)** — aggregate the per-scene `05-tags/` labels across the
     canticle into one canonical, source-spelled node per figure + aliases + provenance, grouping
     scene-local labels by the identity the reading already states (`Poeta`/`ombra` → `Virgilio`).
     This is the one invariant tags deliberately can't hold (ARCH §11) — and it is *reconciliation*
     of two existing resolutions (reading's cross-scene identity + tags' source spelling), NOT a
     re-resolution of WHO.
   - **Edge derivation** — speaker/addressee per quote by a **deterministic join** of the
     dante-corpus quote spans × resolved tags (a span's first-person tag's referent is the speaker;
     child spans excluded so reported speech separates cleanly), plus `bullets`'s "who did what" as
     proto-relations. Code joins on tag numbers (ARCH §14); a weak model only for residuals a join
     can't settle.
   - **Why measure before speccing:** designing the layer ahead of the data is the trap to avoid.
     The shape of this layer (pure code vs. a small model step) should be decided from the
     now-measurable residuals: how often identity is already pinned by the reading; what fraction of
     quotes carry an internal first-person tag (= the join's coverage); how many epithets never
     co-occur with their proper name. **Evaluation pending — measure before locking a spec.**

## Pipeline (data flow)

```
  dante-corpus (shared inputs, via the dante_corpus API — no LLM):
     source cantos ─→ canto.lines() / Line.tokens     normalized lines + tokens   [done]
                   ─→ canto.quotes()                   quote-span tree             [done]

  dante-analyze (this repo — scene data + local-LLM passes):
     01-scenes/<c>/NN.json ─→ load_scenes()               scene line-ranges           [done]
     02-markup/markup.py    ─→ 02-markup/<canticle>/NN.txt      pronoun + name marks    [done; refactored]
                         (single pass, gemma4:31b-it-qat + CoT on, token-boundary normalization)
     03-reading/reading.py  ─→ 03-reading/<canticle>/NN.txt     free prose reading      [done]
                                                           (committed, not proofread, no check)
     04-bullets/bullets.py  ─→ 04-bullets/<canticle>/NN.txt     tag-citing bullets      [done]
                                                           (coverage-checked, reader model)
     05-tags/tags.py        ─→ 05-tags/<canticle>/NN.txt        n. Name source-spelling [done]
                                                           resolution (checked, reader model)
     05-tags/verify_tags.py    (check 05-tags/ vs markup k + reading; --fix re-elides)  [done]
     (downstream) ─→ TBD                            entity reconciliation +  [next: design
                                                    speaker/addressee edges   from residuals]
        ↑ The downstream layer (Active work 1). Its speaker/edge data is intended to feed the
          translation context lock (dante-dravidian).
```

## Scripts — purpose & status

Scene segmentation (`01-scenes/<canticle>/NN.json`) is owned by this repo. The tokenizer and
quote-span tree are provided by **dante-corpus** and consumed through its API.

- **`02-markup/markup.py`** [done] — per-scene reference markup over the corpus source lines.
  Single pass, `gemma4:31b-it-qat` + CoT on — both pronoun (`[..]`/`[+..]`) and name (`{..}`) layers
  in one call. **Model choice**: 31b over 26b — 26b had formatting defects (missing spaces between
  adjacent marks like `[+io][mi]`) and semantic errors (wrong subject pronoun on L29, L114, L65 of
  Inferno 1); 31b's occasional name over-marking is acceptable per "Decisions to keep".
  Post-LLM token-boundary normalization (`normalize_token_brackets`, ARCH §12): LLM outputs like
  `[m]'` where the tokenizer treats `m'` as one token; the function expands the bracket to match
  token boundaries, so bracket edges always align with `dante_corpus.tokenize` output.
  Output: `NN.txt` per canto (committed). Reads source lines from the dante_corpus API; reads scene ranges from `01-scenes/` JSON.
- **`dante_analyze/`** [done] — the shared library for 03-reading/reading.py +
  04-bullets/bullets.py + 05-tags/tags.py + 05-tags/verify_tags.py, split across modules:
  `corpus.py` (corpus input readers: `read_markup`, `load_scenes`, `available_cantos`),
  `checkpoint.py` (`load_readings`, `load_tags`, per-canto `## Scene` + `# recap` I/O),
  `marks.py` (deterministic tag numbering `number_scene`, reply normalizer `unbrace`, elision repair `fix_elision`),
  `llm.py` (the **single runaway-guarded LLM gateway** `call_llm`),
  `prompts.py` (Turn-1 `build_reason_prompt`),
  `cli.py` (read-only query CLI). All re-exported from `dante_analyze/__init__.py`.
- **`03-reading/reading.py`** [done] — free prose reading per scene (bullets's old Turn 1)
  → `03-reading/<c>/NN.txt`. CoT ON, `gemma4:31b-it-qat`; no check, not proofread. Owns the recap.
  Full spec + rationale: README "Scene reading, bullets, and tags", ARCH §1/§11.
- **`04-bullets/bullets.py`** [done] — "who did what" bullets per scene (replays the reading)
  → `04-bullets/<c>/NN.txt`. Coverage-checked; NON-authoritative label layer. CoT ON default,
  `gemma4:31b-it-qat`. Full spec: README, ARCH §11/§13.
- **`05-tags/tags.py`** [done] — authoritative `n. Name` source-spelling resolution per
  scene → `05-tags/<c>/NN.txt`. Binds direct to the reading (bullets not shown); WHO not re-decided,
  spelling only. Structure-checked, no review. Full spec: README, ARCH §11. Feeds the
  downstream consumer (Active work 1).
- **`05-tags/verify_tags.py`** [done] — post-run check of `05-tags/` (no LLM): every scene resolves exactly
  its `{1..k}` tags (vs. markup `k` and the reading's enumeration); flags + `--fix` repairs the
  de-elision over-correction (`la altra` → `l'altra`, U+0027). Shares `dante_analyze` parsing/`ELIDE_RE`.
- **`dante_analyze/cli.py`** [done] — read-only query CLI over the committed outputs:
  `dante-analyze {scenes,reading,bullets,tags} show <canticle> <canto>`.

The cross-scene roster (one canonical node per figure) and the speaker/edge attribution are the
downstream layer, Active work 1 — not yet built.

## Open items

- **Known residual:** `05-tags/verify_tags.py` flags **1** structural item (purgatorio 08 scene 64-81) —
  a pre-existing content discrepancy in the committed outputs; accepted as data per the
  no-hand-proofreading policy. Address during pipeline regeneration.

## Deferred

- **Pronoun-layer marking quality** — local models still make errors on Inferno 1:
  spurious/misplaced `[+pron]` supply (needs clause parsing), non-pronoun bracketed,
  wrong pronoun category/form. The hard classes need a stronger model; the partly-
  checkable classes are deferred pending a reliable pronoun lexicon.
- **Remaining pronoun-layer logic checks** — misplaced-supply detection (`[+..]` not
  immediately before a verb); nominative-only supplied-pronoun check. Both need a
  pronoun lexicon.
- **Diff-only storage** — store only additions vs. the source token list.

## Decisions to keep

- **Source-spelling names** everywhere (`Virgilio`, not "Virgil").
- **No answer leakage**: prompts carry source + general knowledge, never per-item
  answers nor text-derived worked examples — `ARCHITECTURE.md` §8.
- **CoT default policy**: plain text + per-scene + logic-checked retry on the **checkable** passes;
  the **exception is `reading.py`** (uncheckable free prose → CoT ON + `gemma4:31b-it-qat`). The
  general rule and its two safety conditions are ARCH §1.
- **Over-marking is acceptable** for the name layer: the downstream consumer tolerates false
  positives; missing a reference is more harmful.
- **All LLM calls go through one shared gateway** (`call_llm` in `dante_analyze/llm.py`); `llm7shi` is therefore a
  normal runtime dependency of this package (markup keeps its own structured-output path).
- **Formalized reconstruction of the text is a goal**, not only a scaffold: the
  `bullets.py` "who did what" bullets are a deliverable in their own right, so their acceptance
  criteria include coverage and readability, not merely feeding resolution. The ultimate aim is a
  **knowledge graph** of the poem (entities + who-does-what + relations); 03-reading/04-bullets/tags are
  the precursor that produces the referent-resolved material to build it from. **Not building the
  graph yet** — current work is this upstream formalization/resolution stage.
- **The pipeline is an experiment: how far can a LOCAL LLM analyze the work.** The deliverables
  double as a measurement of capability, so the success criterion is **confirming the current
  accuracy of the automated pipeline, not perfecting the output**. Hence **no hand-proofreading**
  (it would mask the model's true accuracy); 03-reading/04-bullets/tags ship as generated and residual
  errors are accepted data. Improving accuracy = changing the *method*, never patching by hand.
  (Mechanism — why the structural checks don't catch WHO-errors — is ARCH §11.)
- **Reading vs. 04-bullets/tags = free interpretation vs. tag-anchored formalization** — two passes,
  two kinds of work; don't fold them back together. Numbered-tag anchoring keeps the formalized
  half verifiable (ARCH §11).

## File structure

| Path | Committed | Description |
|---|---|---|
| `01-scenes/<canticle>/NN.json` | ✓ | Scene ranges + names (committed LLM artifact; built by `01-scenes/scenes.py`) |
| `01-scenes/<canticle>.md` | ✓ | Human-readable scene breakdowns (committed LLM artifact; built by `01-scenes/scenes.py`) |
| `01-scenes/scenes.py` | ✓ | LLM-based scene segmentation builder (dev-only; `uv sync --group dev`) |
| `01-scenes/Makefile` | ✓ | Build target for scene segmentation |
| `pyproject.toml` | ✓ | Package metadata; deps `dante-corpus` + `llm7shi` (both runtime) |
| `ARCHITECTURE.md` | ✓ | Local-LLM scripting patterns shared by every pass here |
| `dante_analyze/__init__.py` | ✓ | Re-exports the shared library public surface |
| `dante_analyze/_paths.py` | ✓ | Anchors the project-root output dirs (03-reading/ 04-bullets/ 05-tags/ 02-markup/) |
| `dante_analyze/corpus.py` | ✓ | Corpus input readers (`read_markup`, `load_scenes`, `available_cantos`) |
| `dante_analyze/checkpoint.py` | ✓ | Per-canto `## Scene` + `# recap` checkpoint I/O; `load_readings`, `load_tags` |
| `dante_analyze/marks.py` | ✓ | Tag numbering (`number_scene`), reply normalizer (`unbrace`), elision repair (`fix_elision`) |
| `dante_analyze/llm.py` | ✓ | Runaway-guarded LLM gateway (`call_llm`), `step_sep`, `MAX_LENGTH`, `LLM_RETRIES` |
| `dante_analyze/prompts.py` | ✓ | Turn-1 prompt builder (`build_reason_prompt`) |
| `dante_analyze/cli.py` | ✓ | Read-only query CLI (`dante-analyze {scenes,reading,bullets,tags} show`) |
| `02-markup/markup.py` | ✓ | Per-scene reference markup — single pass, `gemma4:31b-it-qat` + CoT on |
| `02-markup/Makefile` | ✓ | Build target for markup pass |
| `02-markup/<canticle>/NN.txt` | after regen | Single-pass markup output (committed after pipeline regeneration) |
| `03-reading/reading.py` | ✓ | Free prose reading per scene; CoT on + `gemma4:31b-it-qat`; no check, not proofread |
| `03-reading/Makefile` | ✓ | Build target for reading pass |
| `03-reading/<canticle>/NN.txt` | ✓ | Free reading (committed, not proofread): prose per scene + recap; the checkpoint |
| `04-bullets/bullets.py` | ✓ | "Who did what" bullets per scene (replays the reading); coverage-checked; `gemma4:31b-it-qat` |
| `04-bullets/Makefile` | ✓ | Build target for bullets pass |
| `04-bullets/<canticle>/NN.txt` | ✓ | Tag-citing English bullets per scene (non-authoritative label layer); the checkpoint |
| `05-tags/tags.py` | ✓ | Authoritative `n. Name` source-spelling resolution per scene (binds direct to reading); reader `gemma4:31b-it-qat`; structure-checked |
| `05-tags/verify_tags.py` | ✓ | Post-run check of `05-tags/` (no LLM): `{1..k}` tag-count agreement; `--fix` re-elides over-corrected labels (U+0027) |
| `05-tags/Makefile` | ✓ | Build targets for tags pass + verify |
| `05-tags/<canticle>/NN.txt` | ✓ | Per-tag source-spelling resolution (committed, the data downstream consumes); the checkpoint |

The normalized source `.txt`, tokens, and quote-span XML live in **dante-corpus** and are read
through its API. Scene JSON (`01-scenes/<canticle>/NN.json`) lives in this repo.

## Digest edition (future)

Goal: a retelling of each canticle that is **more detailed than a bare plot summary but lighter
than a full line-by-line translation**, at a granularity where the plot can be read as a story.
It is an **analyze-side deliverable** — derived from `03-reading/` (which already resolves WHO per
scene) — not a translation product.

- **Density**: **one to two sentences per scene** — enough to convey who acts and what happens,
  while skipping the dense doctrinal and prosodic detail of the full text.
- **Unit**: scenes are **grouped into paragraphs**, several scenes per paragraph, roughly **3–5
  paragraphs per canto**. A scene is *not* its own paragraph; the per-scene sentences flow
  together into continuous narrative prose.
- **Source of truth**: `03-reading/` carries the referent-resolved prose; the source text and corpus
  scene split (`dante-corpus`) anchor it to the canonical text.
- **Form**: prose paragraphs under `## Canto N` headings.

### Pipeline

The digest is **narrative prose**: it deliberately breaks line fidelity, so it is its own
prose-generation pass with its own check — **narrative coherence + factual accuracy** — not a
coverage/word-table check. Keep it cleanly separate from the translation pipeline.

### Inputs

- `03-reading/<canticle>/NN.txt` — referent-resolved scene readings (primary source of truth).
- `01-scenes/<canticle>/NN.json` — scene ranges for grouping into paragraphs (this repo).
- `01-scenes/inferno.md` / `purgatorio.md` / `paradiso.md` — scene breakdowns (this repo;
  per-scene summaries are *incidental*, not authoritative).

### Deferred

- If a vetted translation later exists it could enrich the digest, but the digest does not
  depend on one.
