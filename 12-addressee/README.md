# 12-addressee — who each speech span is directed at (context-lock Step 4)

The dialogue analogue of the speaker join `06-speech` already made. The action-only KG (`08-kg`) and
`06-speech` record the **speaker** of every quote span but never the **addressee** — who the speaker
is talking *to*. Addressee is narrative state the action-only KG does not carry; the lock must fix it
(`../PLAN.md` "addressee per speech span"). This pass supplies it as its own single text-derived
judgment, one judgment per script, so judgments never contaminate each other.

## How it works — code-first, LLM only for the residual

The `06-speech` method: code resolves every unambiguous case, the LLM is invoked **only** on genuine
ambiguity. For each **attributed** `06-speech` span, the candidate addressees are the **present** cast
of the span's scene (`11-presence`, `status: present`) minus the speaker — a closed set already
resolved upstream. The candidate count alone decides the path:

- **0 candidates** → `addressee: (none)`, `source: none`. The speaker is the only present figure:
  soliloquy, or address to an absent / merely-mentioned figure. Address-to-absent is **out of scope**
  (the pool is present-only), recorded as `(none)`, never guessed — no LLM.
- **1 candidate** → that figure, `source: code`. The two-person-scene case: deterministic, no LLM.
- **≥2 candidates** → the LLM chooses one from the **closed candidate list**, `source: llm`.

Spans whose speaker is `(unattributed)` carry no line. The LLM is thus confined to an oracle role —
"which of these present figures is addressed" — over a set the pipeline already fixed; everything
else (gathering the pool, normalization, the closed-set/geometry checks, coverage, resume) is code.

### The LLM path (ambiguous spans only)

1. **Pool (code).** `present_cast` ∩ scene minus the speaker by `fold_key` (the same join `08-kg`
   uses), so a cosmetic spelling drift is tolerated and rendered back to the canonical present-cast
   label. This is the closed set the model must choose from.
2. **Choose (LLM, one turn per span).** The numbered scene source with the span lines marked, the
   speaker, and the closed candidate list; the model returns one addressee plus a `basis` line. CoT is
   **on** by default (`--no-think` disables): addressee is a coreference judgment ("use the strongest
   reader for coreference"), the reasoning runs in Ollama's thinking channel, `call_llm` caps runaway.
   Examples are schematic (the FORM only) — never a figure from the span under test, so no answer
   leaks in.
3. **Check (code), retried in-conversation** (max 3 attempts, last draft kept flagged):
   - **closed-set (fatal):** the addressee is in the candidate pool by `fold_key`, ≠ speaker.
   - **basis geometry (fatal):** the `basis` range lies within the span's lines.
   - **cross-scene (soft, warning):** a span flagged `cross-scene` is logged — it is attributed to the
     scene where its speech *begins*.

   Whether the choice is *correct* is interpretation, shipped as generated — no hand-proofreading
   (improve the method and re-measure instead).

## Inputs / outputs

```
Input:  02-markup/<canticle>/NN.txt   (source lines), 01-scenes JSON (load_scenes),
        06-speech/<canticle>/NN.txt   (attributed spans = the units),
        11-presence/<canticle>/NN.txt (present cast = the candidate pool)
Output: 12-addressee/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of addressee lines
        (the file is the checkpoint: a finished scene is skipped on resume; delete to regenerate)
```

### Scene block

```
## Scene 1-9: The Inscription on the Gate
- 3:1 lines 1-9 | speaker: la porta dell'Inferno | addressee: chiunque entri nell'Inferno | source: llm | basis: 9-9

## Scene 10-18: Virgil's Interpretation
- 3:12 lines 12-12 | speaker: Dante | addressee: Virgilio | source: code | basis: 12-12
- 3:14 lines 14-18 | speaker: Virgilio | addressee: Dante | source: code | basis: 14-18
```

- `quote_id` / `lines s-e` — the `06-speech` span, grouped under the scene containing its start line;
- `speaker` / `addressee` — canonical node labels (source spelling, matching the KG nodes; per the
  `../PLAN.md` name-form rule), or `(none)` for the empty-pool case;
- `source` — `code` | `llm` | `none`, how the addressee was decided;
- `basis` — the source line range supporting it (the span lines for the code path, the LLM-cited line
  for the ambiguous path; a line reference, so the checkable core is not a fragile string).

A scene with no attributed span writes the `# (no attributed speech in this scene)` marker.

Read downstream with `load_addressee(canticle, canto)` → `{(s,e): [{quote_id, start, end, speaker,
addressee, source, basis_start, basis_end}, …]}` (in `dante_analyze.checkpoint`, beside
`load_presence`).

## Run

```bash
uv run 12-addressee/addressee.py inferno [-c 1] [-m MODEL] [--no-think]
make -C 12-addressee        # all three canticles (sequential)
```

Model: `ollama:gemma4:31b-it-qat` by default (the stronger reader); the build was produced with a
Gemma-4-31B cloud endpoint (`-m`). **Parallel-safe by canticle:** the only write target is
`12-addressee/<canticle>/NN.txt`, so per-canticle runs write to disjoint subdirectories over
read-only inputs and can run concurrently (one process per canticle).

## Measured result

Full build, all 100 cantos — `488` attributed speech spans, coverage **exact** (every attributed
`06-speech` span yields exactly one line: 203 / 187 / 98), every line passing the closed-set and
basis-geometry check (`0` flagged):

| canticle | cantos | spans | code | llm | none |
|---|---|---|---|---|---|
| inferno    | 34 | 203 |  98 |  92 | 13 |
| purgatorio | 33 | 187 | 107 |  67 | 13 |
| paradiso   | 33 |  98 |  58 |  16 | 24 |
| **total**  |100 | 488 | 263 | 175 | 50 |

- **Code carries the majority.** `263` of `488` spans (53.9%) resolve with no LLM call — `(none)`
  empty-pool plus single-candidate two-person scenes — and only `175` (35.9%) reach the oracle. The
  candidate-count split *is* the source split: `none` = 0 candidates, `code` = exactly 1, `llm` = ≥2,
  so the table also reads as how often each scene's present cast left the addressee genuinely open.
- **The LLM share tracks how crowded the staging is.** Inferno has the highest `llm` rate (92/203,
  45.3%) — its infernal scenes routinely put ≥3 figures on stage (pilgrim, guide, and a crowd or a
  third soul), so the addressee is genuinely ambiguous and code cannot decide it. Purgatorio's mix of
  two-person climbs and group encounters tips back toward `code` (107/187, 57.2%).
- **Paradiso speaks less, and more often to no present candidate.** It has barely half the spans of
  Inferno (98) — far less face-to-face dialogue — and the highest `none` rate (24/98, 24.5%): its
  discourse is dominated by prayer, invocation, and apostrophe to absent or divine figures, exactly
  the address-to-absent the present-only pool puts out of scope. Its `llm` rate is lowest (16.3%):
  few of its scenes crowd ≥2 present figures around a speaker.

Spotlight on **Inferno 3** (the LLM path's reference case): the gate inscription
`la porta dell'Inferno` addresses `chiunque entri nell'Inferno` (`llm`, from a 3-figure pool also
holding Dante and Virgilio); the Dante↔Virgilio exchanges resolve `code` or `llm` to the non-speaker;
and at the Acheron `Caronte` addresses the `anime prave` (`llm`) — the model correctly picks the
crowd over the two protagonists, the discrimination code cannot make. Every present-only pool the
canto offered the oracle was chosen from in-set.

## Notes

- `load_addressee` and `ADDRESSEE_LINE_RE` live in `dante_analyze/checkpoint.py`, beside
  `load_presence` — reused parsing belongs in the package, not in a pass script (ARCHITECTURE
  "Shared Code"; feedback memory `feedback_shared_library_reuse`).
- No carry-forward / recap: addressee is a per-span judgment within a scene, not narrative state that
  persists, so the driver is the bare per-scene checkpoint loop (like `11-presence`).
- The present-only candidate pool is a deliberate scope cut: apostrophe / address-to-absent /
  address-to-reader (a prayer to an absent Beatrice, the narrator's address to the reader) does not
  resolve to a present candidate and is recorded `(none)`, not guessed — `misnames-addressee`
  dramatic-irony flags and `13-cohort` / `14-lock` (the join) are separate later passes.
