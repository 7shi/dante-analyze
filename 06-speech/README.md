# 06-speech — speaker per quote span (KG Step 2)

`04-tags` resolved WHO each tag is, per scene; `05-registry` folded those per-scene labels into one
canonical node per figure. This pass is the first KG *edge* layer: for every quote span in the poem
it decides **who is speaking**, by reading the first-person referents that fall inside the quote's
own region and joining them onto the registry's canonical nodes. The speaker edges feed the relations
pass and KG assembly, and the translation context lock (`dante-dravidian`).

It is **pure code, no LLM** — the work is geometry (which tags lie inside which quote) plus a join.
`05-registry/measure.py` already sized this exact computation (its column-aware quote-coverage probe);
this pass turns that measurement into committed, canonicalized, structure-checked output.

## What it does

For each canto, over `dante_corpus`'s quote forest (`canto.quotes()`, walked depth-first,
parent-before-children):

1. **Gather referents.** Per scene, `number_scene` gives each tag's `(kind, surface)` and
   `tag_positions` its `(line, col)` in the *source* (column-aligned). Each tag's `04-tags` label is
   `norm_label`'d, then **canonicalized through the registry** (`fold_key(label) → canonical
   heading`, built once from `load_registry`). A label that maps to nothing (only `(unknown)`, which
   the registry dropped) contributes no referent.
2. **Attribute per span.** Collect the canonical referents whose `(line, col)` lies in the span's
   **own region** (`quotespans.own_region` — inside the span but inside none of its children, so a
   nested quote belongs to the child). Bucket each by first-person surface
   (`FIRST_PERSON_{STRONG,WEAK,PLURAL}` from `labels.py`).
3. **Speaker / signal / flags** (canonicalize BEFORE the uniqueness test, so two spellings of one
   figure collapse to one speaker, not `multi`):
   - unique **strong** first-person (`io`/`i'`/`ïo`) referent → that speaker, `signal: strong`;
   - more than one distinct strong referent → `(unattributed)`, `signal: none`, flag
     `multi(<a>;<b>;…)`;
   - else unique **weak** first-person (`mi`/`me`/…) referent → that speaker, `signal: weak`;
   - else `(unattributed)`, `signal: none`; flag `plural` if only plural first person was found;
   - orthogonal flag `cross-scene` when the span crosses a scene boundary.

**Coverage is measured data, not a target.** Most spans are `(unattributed)` in v1 (the registry
gives a canonical speaker only when a first-person pronoun actually pins one inside the quote); that
is expected, not a bug. The signal counts reconcile exactly with
`05-registry/measure.py`'s quote-coverage buckets — canonicalization can only *merge* distinct raw
referents into one speaker, so `signal: strong` can rise above the raw `strong-unique` count, never
fall.

Over the full committed corpus, `05-registry/measure.py` measures **1,222 quote spans**, resolved by
**code alone** (column-aware, before any registry join) as: strong-unique 395 / multi-strong 28 /
weak-only 90 / plural-only 68 / none 641 — so ~32% pin a unique strong first-person speaker without
the registry. After the registry canonicalization this pass adds, the committed signal counts
reconcile to: **strong 398** (≥ the raw 395 — canonicalization only merges), **weak 90**, **none
734** (= 641 none + 68 plural-only + 25 residual multi-strong). Columns matter: single-line quotes
resolve exactly because tag positions carry source columns, not just line numbers.

### Output (`<canticle>/NN.txt`, committed)

One line per quote span, in depth-first walk order; `quote_id` is `dante_corpus`'s `<canto>:<start>`:

```
# Canto 01 — The Dark Wood and the Encounter with Virgil
- 1:65 lines 65-65 | speaker: Dante | signal: weak | flags: -
- 1:67 lines 67-78 | speaker: Virgilio | signal: strong | flags: cross-scene
- 1:79 lines 79-80 | speaker: (unattributed) | signal: none | flags: -
```

Downstream reads it with `load_speech(canticle, canto)` → `[{quote_id, start, end, speaker, signal,
flags}, …]` (`dante_analyze/checkpoint.py`).

## Checks

- **Round-trip guard (warn).** Per line, `marks.strip_to_source(markup_line)` (whitespace-collapsed)
  must equal the source `canto.line(n).text`, confirming the column math the attribution rests on.
  The ~10 corpus-wide nested-brace lines (e.g. `{figliuol d'{Anchise}}`) surface here as an accepted
  ≤1-column anomaly — printed as `WARN`, not aborted.
- **Structural check (fail-loud, non-zero exit).** Every quote span is emitted exactly once by id
  (`walk_spans(canto.quotes)` vs the file's ids), and every attributed speaker (≠
  `(unattributed)`) is a node in `load_registry(canticle)`. Skipped under `--raw`.

## Usage

```bash
make -C 06-speech                              # build all three canticles + fail-loud check
uv run 06-speech/speech.py inferno             # one canticle
uv run 06-speech/speech.py inferno --raw       # raw norm_labels, no registry join (early testing)
uv run dante-analyze speech show inferno 1     # read a committed file
```

`--raw` emits the raw `norm_label` speakers and skips the registry join + speaker-in-registry check,
for testing without (or before) a committed registry. The committed output is always the canonical
(non-`--raw`) build. The Makefile is pure code — no `model.mk`, no LLM.
