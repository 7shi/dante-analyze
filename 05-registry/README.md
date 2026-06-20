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

## `registry.py` — build the node table (pure code)

**Purpose.** Aggregate `04-tags` into `05-registry/<canticle>.txt`: canonical nodes with type,
labels, and surface aliases. The build calls **no model** — node TYPES are read from
`04-tags/types.txt`, produced upstream by `04-tags/node_types.py`. Pipeline:

```
gather (code) -> fold-merge (code) -> alias-merge (code) -> set-resolve (code) -> read types (code)
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

**3. Node typing (read the cache, pure code).** Each non-set node's type comes from the typing cache
`04-tags/types.txt` (`load_types_cache`), produced upstream by the LLM step `04-tags/node_types.py`
(see `04-tags/README.md`). The build only **reads** it and fails loud if any node is untyped (run
`node_types.py` first). The cache is overlay-free — a superset of every label ever seen — so every
node rendered here resolves to a type.

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
*different* figures in different scenes, so no global alias is correct. `04-tags/coreference.py`
decides, per scene and with the scene's reading as context, which fuller-form figure (if any) the
label denotes, and stages a per-tag correction in `04-tags/coref.txt`:

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
- **candidates are read from the overlay-free `04-tags/types.txt`, never from the `<canticle>.txt`
  node set.** The node set is built *with* this overlay applied, so reading it would make
  `coreference.py` depend on its own downstream output (a build-time cycle). The typing cache is built
  overlay-free one step upstream, keeping the whole identity build a single linear DAG:
  `tags.py` → `node_types.py` (`types.txt`) → `coreference.py` (`coref.txt`) → `registry.py`;
- the safe default is **`distinct`** — no correction, label left as committed;
- every decision (incl. `distinct`) is recorded in `04-tags/coref.cache.txt` for resume/audit;
  only non-`distinct` decisions reach `04-tags/coref.txt`;
- **the overlay is staged for human review before commit.** Read it, delete wrong lines, then
  rebuild the registry — the structural check rejects any correction pointing at a non-existent
  canonical, but it cannot catch a plausible-but-wrong merge, so the human pass is the real gate.

**Where the generator lives.** `coreference.py`, the overlay `coref.txt`, and the audit cache
`coref.cache.txt` all live in **`04-tags/`**: the output is a *tags* patch, so the writer sits with
the data it corrects and with `load_tags`, the reader that applies it. Its typing input is now a
04-tags **sibling** (`types.txt`, produced one step upstream by `node_types.py`); its only remaining
05-registry input is the hand-maintained `aliases.txt`, read as **data** via the shared
`load_types_cache` / `load_aliases` — no cross-pass code import, and 05-registry never writes into
04-tags.

Run `make -C 04-tags typing` (if `types.txt` isn't current), then `make -C 04-tags coref` to
(re)generate, **review** `04-tags/coref.txt`, and rebuild with `make -C 05-registry`. The build is a
straight line — `tags → node_types → coref → registry` — with no re-render: `registry.py` only reads
the overlay. With an absent or empty `04-tags/coref.txt`, `load_tags` is a no-op and the registry is
byte-identical.

**Run `coreference.py` as ONE process — do not parallelize per canticle** (same constraint as
`registry.py`). Both outputs are global single files with no locking: `04-tags/coref.cache.txt` is
append-on-decision, and `04-tags/coref.txt` is rewritten whole from the in-memory cache at the end of
the run — concurrent runs corrupt the cache and clobber each other's overlay (last-writer-wins). The
`make -C 04-tags coref` target passes all three canticles to one process.

### `types.txt` — produced upstream, read here

The typing cache `04-tags/types.txt` (`<canonical> = <type>`, committed) is built by the LLM step
`04-tags/node_types.py` and only **read** here via `load_types_cache`. Its resume, single-process,
and rebuild-from-scratch rules live with the producer in `04-tags/README.md`. `registry.py` fails
loud if a node is missing from it (run `node_types.py` first). Because the cache is overlay-free, the
registry render is fully deterministic — pure code, no model call.

---

## Why typing is a node-level pass (not folded into `tags.py`)

A natural question: `04-tags/tags.py` already read each scene and resolved each figure with full
context — why not assign the type there at the same time, instead of a separate node-level pass
(`node_types.py`)? Because the two answer **orthogonal questions** — `tags.py` answers *who* a tag is
(`n. Name`); typing answers *what kind of referent* a figure is (`individual / generic / class /
hypothetical-simile / non-person`) — and the type is structurally a **node** property, not a **tag**
property. (`node_types.py` lives in the `04-tags` directory but operates on the global `Nodes` fold,
the same code-merge the registry uses — it is a node-level pass, not a per-scene one.)

1. **Unit mismatch (redundancy + inconsistency).** `tags.py` is per-scene; a figure like Virgilio
   appears in dozens of scenes. Typing there would re-classify the same figure dozens of times
   (up to 16,030 tag lines) and risk a different type per scene. `node_types.py` types **once per
   node** (~2,550) — the same dedup win that makes the build cheap.
2. **Type needs the global view.** Whether `le anime` is a `generic` group or resolves to specific
   individuals is a property of the figure across the whole work, not of one scene. The type belongs
   *after* the `fold_key` merge that produces the canonical node — you type the node, not each raw
   spelling.
3. **One kind of work per pass.** `tags.py`' check is "every tag named once, no
   pronoun echo"; typing's check is "type in vocabulary". Folding an ontological classification into
   the per-tag identity turn would complicate both checks and both prompts. The project keeps reading
   / tags / typing / registry as separate narrow passes on purpose.

**The real tradeoff.** Typing sees only the bare label, so it has *less* context than `tags.py` had
when it understood the figure in its scene. That is a deliberate trade: we give up context to gain
dedup, global consistency, and a cheap, checkable pass. If typing accuracy proves insufficient, the
fix is **not** to fold it back into `tags.py` per scene (that breaks the dedup) but to feed the
node-level pass more signal while still typing once per node — e.g. attach the node's surface aliases
(already computed) or a few representative scene contexts to the prompt. Per the project's
method-not-handwork policy, accuracy is improved by changing the method, never by per-item patching.

---

## make targets

| Target | Command it runs | Effect |
|---|---|---|
| `make -C 05-registry all` | `registry` | Same as `registry` — the build is a single pure-code render now (no cross-dir chain, no re-render) |
| `make -C 05-registry registry` | `uv run registry.py inferno purgatorio paradiso` | Build the three `<canticle>.txt` (pure code, no model); reads `04-tags/types.txt` for node types and applies whatever `04-tags/coref.txt` holds |
| `make -C 04-tags typing` | `uv run node_types.py inferno purgatorio paradiso -m $(MODEL)` | (Upstream, LLM) (re)build the typing cache `04-tags/types.txt`; prerequisite for `coref` and `registry`. See `04-tags/README.md` |
| `make -C 04-tags coref` | `uv run coreference.py inferno purgatorio paradiso -m $(MODEL)` | (Upstream, LLM) (re)generate the per-tag coreference overlay `04-tags/coref.txt` for human review (Fix 2); reads `04-tags/types.txt`, so run `make -C 04-tags typing` first |
| `make -C 05-registry measure` | `uv run measure.py` | Re-print the sizing report + decision gates (read-only) |

`$(MODEL)` comes from `../model.mk` (default `ollama:gemma4:31b-it-qat`); `registry.py` itself takes
no model (pure code).

## Usage

```bash
make -C 05-registry measure                 # size the problem (read-only)
make -C 05-registry registry                 # build the node tables (pure code; fail-loud check)
uv run 05-registry/registry.py inferno       # one canticle (still gathers all three globally)
uv run dante-analyze registry show inferno   # read a committed registry file
```

The full from-scratch identity build is a straight line across the two directories:

```bash
make -C 04-tags          # tags.py        (LLM)
make -C 04-tags typing   # node_types.py  (LLM) -> 04-tags/types.txt
make -C 04-tags coref    # coreference.py (LLM) -> 04-tags/coref.txt   (then review it)
make -C 05-registry      # registry.py    (pure code) -> 05-registry/<canticle>.txt
```

Downstream reads it with `load_registry(canticle)` → `{canonical: {type, labels, surfaces,
members, grouped}}` (`dante_analyze/checkpoint.py`).
