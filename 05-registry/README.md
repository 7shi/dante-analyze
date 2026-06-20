# 05-registry — canonical node table (KG Step 1)

`04-tags` resolves WHO *per scene*, so the same figure can carry different spellings in
different scenes (`Virgilio`, `quel Virgilio`, `'l mio maestro`, …) and the same epithet can
recur unlinked across scenes. The registry is the first pass that sees **every unit at once**:
it folds those per-scene labels into **one node per figure across all three
canticles**, picks a canonical spelling, assigns a node **type**, and attaches the figure's
**surface aliases** with counts. This node set is what `06-speech` and the relations pass join
onto by `fold_key`.

There are two scripts here. `measure.py` is a **read-only probe** that sized the problem and
froze the design *before* any prompt existed; `registry.py` is the **builder** that follows the
design `measure.py` validated.

---

## `measure.py` — size the problem first (no LLM, writes nothing)

**Purpose.** A pure-code stdout report over the committed `04-tags`: how many distinct labels,
how head-concentrated, how many collapse by `fold_key`, how many comma-labels are real sets vs.
epithets, how much `(unknown)`/typo noise, and how well quote spans resolve to a first-person
speaker. It ends with **decision gates** that say whether the LLM residual is tractable.

**Background (why measure first).** The original plan was a single per-canticle LLM call to
*group* epithet variants. Measuring the full output showed that call cannot hold the residual:

```
$ make -C 05-registry measure        # or: uv run 05-registry/measure.py
...
# GLOBAL totals (all canticles)
  tag lines: 16030
  distinct labels: 2923
  fold_key code-merge: 2923 labels -> 2712 nodes (... merge ...)
  epithet nodes occurring >=2x (per-canticle gate input): ... global

## Decision gates
  [PASS] base figures with longer forms < 50:   ... (fuzzy gate)
  [FAIL] epithet nodes/canticle < 150:           inferno=285, purgatorio=312, paradiso=330
  => LLM residual: REVISIT — gate failed; epithet grouping likely needs
     batching/sub-passing rather than one call per canticle (see report body)
```

The lessons are measure the consolidation residual on the *full* output, split the deterministic
code-merge from the LLM residual, and prefer flagged singletons over an unverifiable merge.
It is what produced **option A** below. `measure.py` is kept as a re-runnable
regression: rerun it after any `04-tags` change to confirm the gate numbers still hold.

---

## `registry.py` — build the node table (the one LLM stage is typing)

**Purpose.** Aggregate `04-tags` into `05-registry/<canticle>.txt`: canonical nodes with type,
labels, and surface aliases. Pipeline:

```
gather (code) -> fold-merge (code) -> alias-merge (code) -> set-resolve (code) -> type (LLM, cached)
              -> render per-canticle (code) -> structural check (code)
```

`fold_key` only merges cosmetic drift (case, articles, elision). Two further identity layers handle
what it cannot — see **"Identity resolution beyond fold_key"** below.

**1. Gather + fold-merge (pure code).** Read every scene's labels (`load_tags`) and surfaces
(`number_scene` `meta`), normalize (`norm_label`), group by `fold_key`. The canonical label is the
**most frequent original spelling** in the group. This deterministically collapses 2,922 spellings
→ **2,711 nodes** (the `(unknown)` fold is dropped). Canonical labels are decided **globally** over
all three canticles, so a cross-canticle figure (Dante, Virgilio, Beatrice, biblical/classical
names) is **one node, typed once** — not re-derived per canticle. Even when you build only one
canticle, all three are gathered first so the labels stay consistent.

**2. Set resolution (pure code).** A comma-label whose every piece is a known node or a
capitalized name (`split_set`) is a **set** node — a structural kind orthogonal to the five types —
listing its members instead of surfaces.

**3. Node typing (LLM, cached).** The *only* LLM stage. Each non-set node is classified once with a
closed vocabulary — `individual | generic | class | hypothetical-simile | non-person` — in batches
of 20, reply `n. <label> = <type>`. Checked (every label typed once, type in vocabulary, label
echoed verbatim) with pinpointed in-conversation retry, exactly like `tags.py`. `gemma4:31b-it-qat`,
CoT on. ~2,550 nodes ÷ 20 ≈ **~128 calls** total — far fewer than typing per scene or per canto,
which would re-type recurring figures hundreds of times.

A concrete batch the model sees and answers:

```
1. Dante = individual
2. la Fortuna = non-person
3. angeli = class
4. Beatrice = individual
```

**4. Render + check (pure code).** Write `05-registry/<canticle>.txt`. Surfaces and labels are
**per-canticle** (each file is self-contained); the canonical label and type are global, re-emitted
in each canticle file the node appears in. The structural check (fail-loud, non-zero exit) confirms:
every distinct `04-tags` label in the canticle is assigned to exactly one node, every set member
resolves, every type is in vocabulary, every heading is one of its group's raw labels.

### Output example (`inferno.txt`)

```
# Registry — inferno

## Virgilio
- type: individual
- labels: Virgilio
- surfaces: tu (96), ei (86), io (68), elli (50), Maestro (22), ..., quel Virgilio (1)

## Dante, Virgilio
- type: set
- members: Dante | Virgilio

## gente
- type: individual
- labels: gente
- surfaces: ...
- grouped: no
```

**Option A — `grouped: no`.** Epithet grouping is **skipped in v1** (the gate it failed). Every
non-name, non-set node keeps its own node, flagged `- grouped: no` to mark the un-consolidated
epithet layer. A flagged singleton is safer than a merge the structural check cannot verify;
consolidation is a later pass. The rejected alternative (B) was to split
each canticle's ~300-candidate list into several grouping calls — more design and tokens, with
cross-batch splits a single call would have caught, and still no check that can verify a merge.

---

## Identity resolution beyond fold_key

`fold_key` merges only cosmetic drift. Genuinely-different labels for the same figure need more.
There are two layers, by increasing risk. Both are motivated and measured in the root `KG-PROBLEM.md`
(the downstream impact of a node-set change).

### Fix 1 — `aliases.txt` (deterministic, global)

A hand-maintained merge table, `05-registry/aliases.txt`, with one `alias = canonical` per line.
`apply_aliases` (in `registry.py`, between fold-merge and set-resolve) folds the alias node's labels
and surfaces into the canonical and drops the alias. Both sides must be existing nodes — a typo
raises rather than silently no-ops. This is for **spelling variants with zero ambiguity risk**: one
surface that *always* means one figure, so a global merge is safe and fully verifiable. The four
committed pairs:

```
Mastro Adamo   = Maestro Adamo
Pier delle Vigne = Pier della Vigna
Pietro Damian  = Pietro Damiano
Iesù Cristo    = Cristo
```

### Fix 2 — `04-tags/coref.txt` (context-aware, per-tag)

The opposite case: an **under-specified** label (bare `Guido`, `Latino`, `Pietro`) that means
*different* figures in different scenes, so no global alias is correct. `coreference.py` decides,
per scene and with the scene's reading as context, which fuller-form figure (if any) the label
denotes, and stages a per-tag correction in `04-tags/coref.txt`:

```
inferno/27/19-30/5 = Guido da Montefeltro    # canticle/canto/start-end/tag_no = identity-first label
```

**Why the correction lives at the tag-read layer, not in the registry.** The downstream join
`raw_to_canonical` is a global `fold_key → canonical` map; it *cannot* route one surface (`Guido`)
to two nodes. So the disambiguation has to be in the label itself, applied where every consumer
reads it — `load_tags` (`load_coref`). Once a tag's label is identity-first, the existing fold_key
join folds it onto the right node automatically; **06-speech, 08-kg, and 11-presence need no
change.** This is the same identity-first rule the project applies everywhere ("commit the most
specific identification the reading establishes").

**This step calls the model and cannot be structurally verified** — a wrong merge passes every
check, and false positives dominate (most name-sharing pairs are different people). So:

- granularity is **one decision per (label, scene)** (04-tags already keeps intra-scene labels
  consistent), applied to every occurrence of that label in the scene;
- candidate targets for a bare label are the fuller `individual` forms it **heads** as a proper name
  (`Guido` → `Guido da Montefeltro`, …), plus a seed map for semantic pairs (`Iesù` → `Cristo`).
  `heads_name` excludes governed periphrases where the bare name follows a preposition/possessive/
  demonstrative (`l'ombra di Dante`, `Figliuol di Dio`, `vicario suo Cristo`), and `EXCLUDE_BARE`
  drops superclass terms whose fuller forms are distinct figures (`Dio` spans the Trinity persons);
- **candidates are read from the overlay-free `types.txt`, never from the `<canticle>.txt` node set.**
  The node set is built *with* this overlay applied, so reading it would make `coreference.py` depend
  on its own downstream output (a build-time cycle). Using the typing cache keeps the build a linear
  DAG: registry build #1 (empty overlay) → `types.txt` → `coreference.py` → `coref.txt` → registry
  build #2 (overlay applied);
- the safe default is **`distinct`** — no correction, label left as committed;
- every decision (incl. `distinct`) is recorded in `05-registry/coref.cache.txt` for resume/audit;
  only non-`distinct` decisions reach `04-tags/coref.txt`;
- **the overlay is staged for human review before commit.** Read it, delete wrong lines, then
  rebuild the registry — the structural check rejects any correction pointing at a non-existent
  canonical, but it cannot catch a plausible-but-wrong merge, so the human pass is the real gate.

Run `make -C 05-registry coref` to (re)generate, then rebuild with `make -C 05-registry`. With an
absent or empty `04-tags/coref.txt`, `load_tags` is a no-op and the registry is byte-identical.

**Run `coreference.py` as ONE process — do not parallelize per canticle** (same constraint as
`registry.py`). Both outputs are global single files with no locking: `coref.cache.txt` is
append-on-decision, and `04-tags/coref.txt` is rewritten whole from the in-memory cache at the end of
the run — concurrent runs corrupt the cache and clobber each other's overlay (last-writer-wins). The
`coref` make target passes all three canticles to one process.

### `types.txt` — the resume cache

Typing is the slow part (~128 local-LLM calls), so each passed batch is appended to
`05-registry/types.txt` as `<canonical> = <type>`. On rerun, already-typed nodes are skipped and
only the remainder is sent. Interrupting the build loses at most the one in-flight batch.

`types.txt` is **committed** alongside the three `<canticle>.txt` (it is the exact record of the
LLM's typing decisions): keeping it makes the registry reproducible without re-running the model and
leaves the only interpretive step auditable. To re-derive types from scratch, delete it first.

- **Resume:** rerun `make -C 05-registry` (or the `uv run` command below). It reads `types.txt`,
  skips what's done, and finishes the rest, then renders + checks.
- **Rebuild from scratch:** `rm 05-registry/types.txt` first, then run.
- **Progress:** `wc -l 05-registry/types.txt` (one line = one typed node).

**Run it as ONE process — do not parallelize per canticle.** Typing operates on the *global*
deduplicated node set (the canticle args only choose which `<canticle>.txt` get *rendered*, not what
gets typed). Running `registry.py inferno`, `registry.py purgatorio`, `registry.py paradiso`
concurrently would each re-type the *same* ~2,550 nodes (3× the LLM cost) and **append to
`types.txt` at the same time, corrupting the cache** (it is a plain append-on-pass file, no locking).
The intended invocation is the single `registry.py inferno purgatorio paradiso` that `make` runs;
the three output files are a cheap rendering split at the end of that one run.

---

## Why typing lives here, not in 04-tags

A natural question: `04-tags` already read each scene and resolved each figure with full context —
why not assign the type there at the same time, instead of a separate node-level pass here? Because
the two passes answer **orthogonal questions** — `04-tags` answers *who* a tag is (`n. Name`); typing
answers *what kind of referent* a figure is (`individual / generic / class / hypothetical-simile /
non-person`) — and the type is structurally a **node** property, not a **tag** property:

1. **Unit mismatch (redundancy + inconsistency).** `04-tags` is per-scene; a figure like Virgilio
   appears in dozens of scenes. Typing there would re-classify the same figure dozens of times
   (up to 16,030 tag lines) and risk a different type per scene. Here it is typed **once per node**
   (~2,550) — the same dedup win that makes the build cheap.
2. **Type needs the global view.** Whether `le anime` is a `generic` group or resolves to specific
   individuals is a property of the figure across the whole work, not of one scene. The type belongs
   *after* the `fold_key` merge that produces the canonical node — you type the node, not each raw
   spelling.
3. **One kind of work per pass.** `04-tags`' check is "every tag named once, no
   pronoun echo"; typing's check is "type in vocabulary". Folding an ontological classification into
   the per-tag identity turn would complicate both checks and both prompts. The project keeps reading
   / tags / registry as separate narrow passes on purpose.

**The real tradeoff.** Typing here sees only the bare label, so it has *less* context than
`04-tags` had when it understood the figure in its scene. That is
a deliberate trade: we give up context to gain dedup, global consistency, and a cheap, checkable
pass. If typing accuracy proves insufficient, the fix is **not** to move it back into `04-tags` (that
breaks the dedup) but to feed the node-level pass more signal while still typing once per node — e.g.
attach the node's surface aliases (already computed) or a few representative scene contexts to the
prompt. Per the project's method-not-handwork policy, accuracy is improved by
changing the method, never by per-item patching.

---

## make targets

| Target | Command it runs | Effect |
|---|---|---|
| `make -C 05-registry` (`all`) | `uv run registry.py inferno purgatorio paradiso -m $(MODEL)` | Build/resume the registry; writes the three `<canticle>.txt` + `types.txt` |
| `make -C 05-registry coref` | `uv run coreference.py inferno purgatorio paradiso -m $(MODEL)` | (Re)generate the per-tag coreference overlay `04-tags/coref.txt` for human review (Fix 2); rebuild with `all` after |
| `make -C 05-registry measure` | `uv run measure.py` | Re-print the sizing report + decision gates (read-only) |

`$(MODEL)` comes from `../model.mk` (default `ollama:gemma4:31b-it-qat`).

## Usage

```bash
make -C 05-registry measure                 # size the problem (read-only)
make -C 05-registry                          # build/resume; fail-loud structural check
uv run 05-registry/registry.py inferno       # one canticle (still gathers all three globally)
uv run dante-analyze registry show inferno   # read a committed registry file
```

Downstream reads it with `load_registry(canticle)` → `{canonical: {type, labels, surfaces,
members, grouped}}` (`dante_analyze/checkpoint.py`).
