# 15-digest — the digest edition (the context lock's first consumer)

The first **consumer** of the translation context lock (repository `PLAN.md` direction 1), and its
proof. A 1–2 sentence bilingual (English + Japanese) retelling per scene at story-reading density:
more than a plot summary, lighter than a line-by-line translation.

The point is not only the digest but a demonstration that `14-lock` is what keeps a retelling from
getting identities and settings wrong. The lock is the **primary input** — the closed *who/where*
vocabulary — and the digest may not introduce a name, place, or soul-class the lock does not list for
the scene. `03-reading` supplies *what happens*. Identity resolution itself stays the KG's domain
(`04-tags` → `05-registry` → `08-kg`); the digest consumes the resolved result through the lock, it
does not re-resolve. So the no-leak rule does not apply here: the digest is a deliberate consumer of
resolved results, not a resolution pass.

## What it does

Two programs: `digest.py` generates the prose (LLM); `conformance.py` measures it against the lock
(pure code — the proof).

### `digest.py` (LLM) — `15-digest/<canticle>/NN.txt`

Per scene, a two-turn conversation (the "split deliberation from final output" pattern, as `tags.py`
replays the committed reading):

1. **Turn-1 user** = `build_reason_prompt(..., prior="", recap="")` reconstructs the question the
   committed `03-reading` answered; **Turn-1 assistant** = that committed reading (the resolved
   events, replayed).
2. **Turn-2 user** = `build_digest_prompt(..., lock_scene, prior)` asks for the 1–2 sentence English
   retelling, giving the scene's `14-lock` entry as the **closed who/where vocabulary** plus the
   canto's already-finished digest sentences for continuity. → English.
3. A second call (`build_digest_translate_prompt`) renders that English into Japanese, keeping every
   name in **source spelling**, so the conformance vocabulary survives the language change.

Chain-of-thought is **ON** by default (`--no-think` disables it, as in `reading.py`): the digest is
uncheckable free prose, with no structured output for CoT to corrupt. The output file is the
checkpoint — a scene with a non-empty body is skipped on resume; delete the file to regenerate a
canto. Each scene is a `## Scene s-e: name` block with an `en:` and a `ja:` line.

**Italian marking (`mark_italian`).** In the English line, every term drawn from the scene's lock
vocabulary (names, epithets, settings, soul-classes) is wrapped in `*asterisks*`, so the embedded
Italian is visually distinct — as Latin script already makes it in the Japanese line. Deterministic,
code-side normalization (longest term first so a multi-word epithet wraps whole; idempotent), applied
to **storage only** — the Japanese is translated from the clean English first. `--remark` re-applies
it to already-committed digests with no LLM.

### `conformance.py` (pure code) — the proof

For each scene, code builds the closed vocabulary the scene's lock licenses — every word of every
cast figure (and set members), speech party, setting, region, soul-class, and KG-resolved
`refer`/`relations`/`simile` name, casefolded — then checks the committed digest against it. English
is the primary check (Title-case tokens give a clean closed-set membership test; sentence-initial
words and common-English capitals are stopped, possessive `'s` is stripped). Japanese is checked over
its source-spelling Latin runs, which is weaker (word-boundary ambiguity), so the English rate is the
proof. A token outside the lock is a **deviation — measurement data, not something to hand-correct**.

## Shared library hooks

In `dante_analyze` (cross-pass helpers live there, never copied between passes): `build_digest_prompt`
/ `build_digest_translate_prompt` (`prompts.py`), `load_digest` + `DIGEST_LINE_RE` (`checkpoint.py`),
`DIGEST_DIR` (`_paths.py`), all re-exported from `__init__.py`. Reuses `build_reason_prompt`,
`call_llm`, `load_readings`, `load_lock`, `load_scenes`, `read_markup`, `number_scene`, the `## Scene`
block checkpoint helpers (`out_path` / `iter_scene_blocks` / `render_scene_block` / `append_canto` /
`complete_scene_ends`), and `split_set`.

## How to run

```bash
make -C 15-digest                          # generate all three canticles
make -C 15-digest check                    # measure 14-lock conformance (the proof; no LLM)
make -C 15-digest clean                    # remove the generated digests (regenerable)
uv run 15-digest/digest.py inferno -c 1    # one canto
uv run 15-digest/conformance.py inferno    # measure one canticle
uv run dante-analyze digest show inferno 1 # render as paragraphed prose (--lang en|ja|both)
```

`digest show` groups consecutive scenes into reader paragraphs on `14-lock` `location` change (a long
same-location run is split so paragraphs stay roughly 3–5 per canto) and renders the bilingual prose
under a `# Canto N` heading.

## Measured results — lock conformance (the proof)

Full build, all 100 cantos. Every proper name and setting the digest asserts, measured against the
scene's lock vocabulary:

| canticle | in lock | rate |
|---|--:|--:|
| inferno | 5748 / 5758 | 99.8% |
| purgatorio | 5153 / 5183 | 99.4% |
| paradiso | 4856 / 4897 | 99.2% |
| **total** | **15757 / 15838** | **99.5%** |

The lock works as the closed *who/where* vocabulary: a retelling built on it stays inside it. The
digest even reuses the source epithets verbatim (`piè d'un colle`, `loco selvaggio`, `là dove 'l sol
tace`, `quei che con lena affannata…`).

**The residual is not identity/setting drift.** Across all three canticles, no flagged token is a
wrong figure or place. Every deviation is one of:

- **liturgical Latin quotations** the digest carries faithfully — `Miserere`, `Vinum non habent`,
  `Gloria in excelsis`, `Pater Noster`, `Resurgi`/`Vinci`, `Amen`, `Ave`, `Osanna` (the Japanese
  `in`/`non`/`habent` flags are Latin words inside these quotes, picked up as Latin runs);
- **capitalized theological abstractions** — `Divine Charity`, `Incarnation`, `Scripture`, `Eternal
  Love`, `Golden Age`, `Earth`, `Zodiac` — capitalized concepts, not proper names;
- **reverent capitalized pronouns for God** — `Him` / `Himself` / `His`;
- a few **regional adjectives** — `Tuscan`, `Florentine`.

These are exactly the kinds of material the lock does not vocabularize, so they fall outside it by
construction. They are measurement data, kept as-is. Refining the checker (whitelisting liturgical
quotes, adding reverent pronouns to the stoplist) is method polish that would not change the proof:
the lock prevents the drift it is meant to prevent.
