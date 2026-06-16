# The KG ladder, steps 05 → 08

The knowledge graph is built as four narrow passes that deliberately keep *understanding* and
*extraction* apart. Each pass answers one question and defers the join to the next, so the final
assembly (`08-kg`) is pure code — no LLM — and is total by construction.

| Step | Pass | Question it answers | LLM? |
|------|------|---------------------|------|
| 1 | `05-registry` | **What type** is each label-cluster (normalize cosmetics + type)? | yes — typing only |
| 2 | `06-speech` | **Who** is speaking each quote span? | no |
| 3 | `07-relations` | **Who does what to whom** (edges citing `[n]` tags)? | yes |
| 4 | `08-kg` | **Assemble** — join all of the above into a graph. | no |

The narrative below follows the data as it flows downstream, quoting concrete examples from the
committed output at each step.

---

## Step 1 — `05-registry`: normalize labels into nodes, type them

`04-tags` names each tag **per scene** — it resolves what every mark (`[tu]`, `{Virgilio}`,
`'l mio maestro`) refers to, based on the reading — but it does NOT cross-link tags: it never says
"this tag and that tag are the same figure," so the same person can carry different labels across
scenes (`il Navarrese`, `Navarrese`, `Lo Navarrese`). The registry is the first pass that sees
**every unit at once**: it normalizes cosmetic label variants (case-fold + leading-article strip —
`il Navarrese` and `Navarrese` fold into one node), picks a canonical spelling **globally** across
all three canticles, assigns a node **type** (the only LLM stage), and inventories the surface forms
(pronouns, epithets) that the markup carries. This node set is what every later step joins onto by
`fold_key`.

What the registry does **not** do: cross-tag coreference — merging genuinely different labels for
the same figure (bare `Guido` = `Guido da Montefeltro`, `Maestro Adamo` = `Mastro Adamo`) — is not
attempted in v1. See `KG-PROBLEM.md` for the identification gap and its impact on the graph.

**Pipeline:** `gather (code) → fold-merge (code) → set-resolve (code) → type (LLM, cached) → render
(code) → check (code)`. The only LLM stage is typing, and the LLM is only ever asked one thing: a
closed-vocabulary type per node.

- **Fold-merge (pure code)** normalizes cosmetic label variants: case-fold + leading-article strip
  (`la Fortuna`/`Fortuna`, `i Malebranche`/`Malebranche`, `il Navarrese`/`Navarrese`). It collapses
  **2,923 distinct labels → 2,712 nodes** — 149 groups merge 360 labels, all case/article variants.
  The merge is cosmetic only: labels that differ in content tokens (`Maestro Adamo` vs `Mastro
  Adamo`, bare `Guido` vs `Guido da Montefeltro`) stay separate nodes. The canonical label is the
  most frequent original spelling, decided **globally** over all three canticles, so a
  cross-canticle figure (Dante, Virgilio, Beatrice) is one node, typed once.
- **Node typing (LLM, cached)** classifies each non-set node once with a closed vocabulary —
  `individual | generic | class | hypothetical-simile | non-person` — in batches of 20. A concrete
  batch the model sees and answers:
  ```
  1. Dante = individual
  2. la Fortuna = non-person
  3. angeli = class
  4. Beatrice = individual
  ```
  ~2,550 nodes ÷ 20 ≈ **~128 calls** total — far fewer than typing per scene would be.

**Example output (`inferno.txt`)** — the canonical node, its labels, and the surface inventory:

```
## Virgilio
- type: individual
- labels: Virgilio
- surfaces: tu (96), ei (86), io (68), elli (50), Maestro (22), ..., quel Virgilio (1)

## Dante, Virgilio
- type: set
- members: Dante | Virgilio
```

`labels` has one entry because `04-tags` used the name "Virgilio" consistently across scenes (the
readings identify him by name throughout); the `surfaces` are the **text forms** the markup carries
(pronouns, epithets, the name itself) — an inventory, not nodes the registry merged. For figures
whose `04-tags` labels varied cosmetically (`il Navarrese` / `Navarrese` / `Lo Navarrese`),
fold-merge collapses them into one node; for figures whose labels are genuinely different words
(`Maestro Adamo` vs `Mastro Adamo`), they stay separate nodes (see `KG-PROBLEM.md`).

Typing lives here, not in `04-tags`, because the type is a **node** property (a global view of the
figure), not a tag property: typing in `04-tags` would re-classify the same figure dozens of times
(up to 16,030 tag lines) and risk a different type per scene, while here it is typed once per node
(~2,550).

**Measure-first design.** `measure.py` sized the problem before any prompt existed and produced
**decision gates**. Both failed: the near-dupe gate (`base figures with longer forms < 50` → 346)
and the epithet gate (`epithet nodes/canticle < 150` → 285–330). v1 ships **Option A**: epithet
grouping is skipped, and every non-name, non-set node keeps its own node flagged `grouped: no`.
A flagged singleton is safer than a merge the structural check cannot verify. See `KG-PROBLEM.md`
for why the near-dupes are mostly false positives and what the identification gap means for the
graph.

---

## Step 2 — `06-speech`: who is speaking each quote span

With canonical nodes in hand, this pass produces the first KG *edge* layer: for every quote span in
the poem it decides **who is speaking**, by reading the first-person referents that fall inside the
quote's own region and joining them onto the registry's canonical nodes. It is **pure code, no LLM** —
the work is geometry (which tags lie inside which quote) plus a join.

Per span:

1. **Gather referents** — each tag's `04-tags` label is `norm_label`'d then **canonicalized through
   the registry** (`fold_key(label) → canonical heading`).
2. **Attribute per span** — collect the canonical referents whose `(line, col)` lies in the span's
   *own region* (inside the span but inside none of its children, so a nested quote belongs to the
   child), bucketed by first-person surface (`io`/`i'` strong, `mi`/`me` weak, plural).
3. **Speaker / signal** — canonicalize *before* the uniqueness test, so two spellings of one figure
   collapse to one speaker rather than `multi`:
   - unique strong first-person (`io`) → that speaker, `signal: strong`;
   - more than one distinct strong referent → `(unattributed)`, flag `multi(<a>;<b>;…)`;
   - else unique weak → that speaker, `signal: weak`;
   - else `(unattributed)`.

**Example output (`inferno/01.txt`):**

```
# Canto 01 — The Dark Wood and the Encounter with Virgil
- 1:65 lines 65-65 | speaker: Dante | signal: weak | flags: -
- 1:67 lines 67-78 | speaker: Virgilio | signal: strong | flags: cross-scene
- 1:79 lines 79-80 | speaker: (unattributed) | signal: none | flags: -
```

**Measured coverage** (`05-registry/measure.py` sized this exact computation): **1,222 quote spans**,
resolved by code alone (column-aware, before the registry join) as strong-unique 395 / multi-strong 28
/ weak-only 90 / plural-only 68 / none 641. After registry canonicalization the committed counts
reconcile to **strong 398** (≥ 395 — canonicalization only merges, never splits), **weak 90**,
**none 734**. Columns matter: single-line quotes resolve exactly because tag positions carry source
columns, not just line numbers.

Coverage is **measured data, not a target** — most spans are `(unattributed)` in v1, which is
expected, not a bug.

---

## Step 3 — `07-relations`: subject–predicate–object edges per scene

This pass answers the remaining KG question — **who does what to whom** — as line-oriented edges
that cite the `04-tags` tag numbers, so Step 4 joins them onto the registry nodes mechanically. It is
**interpretation-bound** like `04-tags` (CoT on), binds to the committed reading, and is gated by a
structural check with in-conversation retry.

**Why a closed predicate vocabulary (measure-first).** `measure.py` harvested the readings' `-s`
verbs (every English 3sg-present verb ends in `-s` and the readings are written in that tense:
"Virgil **explains**…", "Dante **asks**…"), then subtracted the two non-predicate classes that also
end in `-s`: plural nouns (`souls`, `spirits`) and **meta-discourse** verbs (`describes` 250×,
`explains` 247×, `continues` 168×). The diegetic remainder collapses to **31 canonical predicates**
(`CLOSED_VOCAB`), clearing the ≤40 tractability gate — **one closed list, no grouping pass**
(contrast the registry's epithet gate, which *failed*).

`CLOSED_VOCAB` is the **single source of truth**: `relations.py` does `from measure import
CLOSED_VOCAB`, and both the prompt menu and the structural check read `set(CLOSED_VOCAB)` — there is
no second copy.

**Two turns over one conversation per scene:**

1. Turn 1 — replay the committed reading as the assistant turn over the `number_scene`-tagged scene.
2. Turn 2 — ask for the edge list over that tagged scene.

The cited `[n]` are the **identical** per-scene tag numbers `04-tags` resolved — the pass never
renumbers, which is what makes Step 4's join total.

**Relation-line grammar:**

```
- [<subj>] <predicate> [<obj>] | frame: <literal|simile|prophecy|reported> | lines <a>-<b>
```

**Example output (`inferno/01.txt`)** — all four frames occur:

```
## Scene 22-30: The Swimmer Simile
- [3] compares [1] | frame: simile | lines 22-26

## Scene 31-36: The Appearance of the Leopard
- [1] chases [2] | frame: literal | lines 34-34
- [3] chases [4] | frame: literal | lines 35-36

## Scene 67-75: Virgil's Introduction
- [13] tells [14] | frame: reported | lines 73-73

## Scene 112-120: The Plan for the Journey
- [6] guides [4] | frame: prophecy | lines 113-113
```

**`frame` is structural, not post-hoc**: `literal` = directly narrated event; `reported` = the
*content* of something a character says; `prophecy` = a foretold future event; `simile` = the
figurative side of a comparison. There is deliberately **no `says-that` meta-edge**: a
reported/prophecy/simile proposition is emitted as its *content* edge with the matching frame, and
*who asserted it* is recovered downstream by joining the edge's line range to `06-speech`'s
speaker — the literal speech act (`[a] asks [b]`) is itself a normal `literal` edge.

**Checks prove structure only** — every cited `[n]` exists in the scene's tag set, every predicate ∈
`CLOSED_VOCAB ∪ {relates-to}`, every frame ∈ the four-value set, every `lines a-b` within the scene.
Whether an edge is the *right* relation is interpretation, shipped as generated. Two consequences are
visible in `inferno/01.txt` and accepted as data: Scene 1-12 emits `[1] meets [2]` where both tags
are Dante (a self-relation across distinct tag *numbers* — a "same registry node" filter belongs in
Step 4, where node identity is resolved), and Scene 100-105 (the Veltro) produces no `prophecy` edge
though the prose foretells one.

---

## Step 4 — `08-kg`: assemble the graph (pure code, no LLM)

The last step **joins** the committed upstream outputs into the assembled graph. Every input is read
through the `dante_analyze` `load_*` API; no text is re-interpreted here. Per canticle, per canto,
over `load_relations(canticle, canto)`:

- **Resolve each edge end to a node.** An edge's `lines a-b` falls inside exactly one `04-tags`
  scene (scenes partition the canto), so find that scene, map the cited `[subj]`/`[obj]` through
  `load_tags → a name`, and canonicalize the name through the registry (`raw_to_canonical` →
  `fold_key` → the canonical heading) → the graph **node**.
- **Recover the asserter.** For `reported`/`prophecy`/`simile` edges, the asserter is the speaker of
  the **innermost** `06-speech` quote span containing the edge's line range. `literal` edges are
  narrated → `null`; an `(unattributed)` container also yields `null`.
- **Merge the speech edges** (speaker → quote span) alongside the relation edges.

**Output is per canticle, JSONL** — `nodes.jsonl`, `edges.jsonl`, `speech_edges.jsonl`.

`nodes.jsonl` — `id` is the registry canonical heading; surfaces/labels are dropped (the graph
references nodes by `id`):
```jsonl
{"id": "Dante", "type": "individual", "members": null}
{"id": "Virgilio", "type": "individual", "members": null}
{"id": "Dante, Virgilio", "type": "set", "members": ["Dante", "Virgilio"]}
```

`edges.jsonl` — the `[n]` tags are now resolved to nodes, and the asserter is recovered for asserting
frames:
```jsonl
{"canto": 1, "scene": [49, 60], "subj": {"tag": 2, "name": "la lupa", "node": "la lupa"}, "predicate": "punishes", "obj": {"tag": 3, "name": "Dante", "node": "Dante"}, "frame": "literal", "lines": [52, 52], "asserter": null}
{"canto": 1, "scene": [67, 75], "subj": {"tag": 8, "name": "Virgilio", "node": "Virgilio"}, "predicate": "relates-to", "obj": {"tag": 9, "name": "Augusto", "node": "Augusto"}, "frame": "reported", "lines": [71, 71], "asserter": "Virgilio"}
```

Note how the second edge's `asserter: "Virgilio"` is recovered by joining its `lines [71, 71]` to the
`06-speech` span `1:67 lines 67-78 | speaker: Virgilio` shown in Step 2 — the join that `07-relations`
deliberately deferred.

`speech_edges.jsonl` — the `06-speech` spans carried verbatim:
```jsonl
{"canto": 1, "quote_id": "1:67", "lines": [67, 78], "speaker": "Virgilio", "signal": "strong", "flags": ["cross-scene"]}
```

**Structural check.** Geometry is fatal (every edge in exactly one scene, every cited `[n]` exists);
name→node resolution is tallied, not fatal (an unresolved end is written `node: null` and counted).
In every run so far each unresolved end is a `(unknown)` label the registry rightly dropped.

**Measured result:**

| canticle   | nodes | edges | speech_edges |
|------------|------:|------:|-------------:|
| inferno    | 1045  | 2142  |          500 |
| purgatorio |  936  | 2010  |          495 |
| paradiso   | 1050  | 1604  |          227 |

Geometry: **0 failures** across all 100 cantos. Name→node: **18 unresolved edge ends total**
(inferno 2, purgatorio 10, paradiso 6), all `(unknown)` labels.

---

## Why the ladder is split this way

Each pass does **one kind of work**, with **one check**:

- `04-tags` names each tag per scene (per-tag resolution, bound to the reading); `05-registry`
  normalizes label cosmetics into nodes and types them. These are separate steps: a per-scene
  pass cannot normalize across scenes, and the type is a node property (global), not a tag
  property (per-scene) — folding typing into `04-tags` would re-type the same figure dozens of
  times and risk a different type per scene. Cross-tag coreference (linking genuinely different
  labels for the same figure) is not attempted in v1; see `KG-PROBLEM.md`.
- `06-speech` answers *who is speaking* by geometry + join — pure code, so it can't disagree with
  the registry it joins onto.
- `07-relations` answers *who does what to whom* and cites `[n]` tags rather than resolving them, so
  the interpretive pass never has to know about node identity.
- `08-kg` is the deferred join: total by construction, because the upstream checks (tag numbers stay
  aligned, every cited `[n]` exists, every edge's line range sits in one scene) are exactly what let
  code resolve each edge end to a node mechanically.

The measure-first discipline (`measure.py` in `05-registry` *and* `07-relations`) sizes the LLM
residual on the **full** output before freezing any prompt, and produces decision gates that say
whether the residual is tractable. The registry's epithet and near-dupe gates both **failed** → v1
ships flagged singletons (`grouped: no`); relations' predicate gate **passed** (31 ≤ 40) → one
closed list, no grouping pass.

Accuracy is improved by **changing the method, never by per-item patching**: flagged singletons over
an unverifiable merge; a `node: null` residual that is counted as measurement rather than hand-fixed.
