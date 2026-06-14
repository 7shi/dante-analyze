# 02-markup — person-reference markup

A deliberately **light** pass: it makes every reference to a *person* in the grammar explicit by
adding inline marks on top of the source lines, **without** saying who anyone is. That separation is
the point — markup enumerates the references mechanically and verifiably; `03-reading`/`04-tags`
later decide identity. The marks are what `number_scene` turns into the numbered `[n]` tags every
downstream pass cites.

## What it does

One unified LLM pass per scene (CoT on, `gemma4:31b-it-qat`, via the shared `call_llm` gateway) adds
**two layers at once**:

- **Layer 1 — pronouns.** Wrap every person-standing pronoun in `[..]`, and **supply** every
  pro-drop (omitted) subject as `[+pronoun]` just before its verb —
  `mi ritrovai…` → `[+io] [mi] ritrovai…`.
- **Layer 2 — names.** Wrap every person-referring noun phrase (proper names and the common-noun
  epithets/periphrases that stand for a person) in `{..}` — `{il Veltro}`, `'{l Poeta}`. Over-marking
  is acceptable here (a missed reference is worse than a spurious one).

**Orthography is code's job**: `normalize_token_brackets` expands a `[..]` bracket
to the tokenizer's token boundary in code, so the model is never asked to fix mechanical bracket
quirks.

## Output

`02-markup/<canticle>/NN.txt` — one marked line per source line; the file is both checkpoint and
committed output (its length = the last finished scene's end line, so an interrupted run resumes).
From `inferno/01.txt`, the opening tercets:

```
Nel mezzo del cammin di nostra vita
[+io] [mi] ritrovai per una selva oscura,
ché la diritta via era smarrita.
...
ma per trattar del ben ch'[i'] vi trovai,
[+io] dirò de l'altre cose ch'[i'] v'ho scorte.
[Io] non so ben ridir com' [i'] v'intrai,
```

## Check

The faithfulness guarantee is a **round-trip**: removing the `{..}` braces, then the `[+..]`
insertions and `[]` brackets, must reproduce the source line verbatim (`check_line`). The pass is
two-tier with in-conversation retry (max 3 each): `mark_scene` validates a whole scene and
**accumulates** the lines that round-trip across attempts, then `mark_one_line` re-does any
still-failing line with surrounding context. A line that never validates is left **unmarked** (a
`WARNING`, and shown with a leading `*` in the run's final dump) rather than committed wrong.

The round-trip proves the marks are *faithful to the source*; it does **not** prove they are the
*right* references — pronoun-layer accuracy (spurious/misplaced `[+..]`, wrong category) is a known
residual deferred to a stronger model / a pronoun lexicon. The ~10
corpus-wide nested-brace lines (`{figliuol d'{Anchise}}`) are an accepted ≤1-column anomaly.

## Model

`ollama:gemma4:31b-it-qat` (the strongest local reader), CoT on (`include_thoughts=True`); Ollama
routes the thinking to its own channel so the saved reply stays clean.

## Usage

```bash
make -C 02-markup                              # all three canticles (target is `markup`, not `all`)
uv run 02-markup/markup.py inferno [-c 1] [-m MODEL]
```

Downstream reads it with `read_markup(canticle, canto)` (source lines with marks) and
`number_scene(lines, s, e)` → the numbered `[n]` tags + per-tag `(kind, surface)` meta
(`dante_analyze/marks.py`).
