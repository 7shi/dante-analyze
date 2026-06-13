# 05-registry — canonical node table (build plan)

> **STATUS: in progress.** `measure.py` ✓ done (sizing + decision gates). `registry.py` is **NOT
> built** — blocked on the **epithet-grouping decision** below. On completion, rename this file to
> `README.md` (a built pass's design doc is a README — cf. `04-tags/README.md`).

Scope-narrowed build spec for **Step 1** of the KG (root `PLAN.md`). The registry aggregates the
per-scene `04-tags/` labels into one canonical, source-spelled node per figure across the whole work
(the roster must see every unit — ARCH §11). Sizing/gates are in root `PLAN.md` "Measured baselines";
the headline that drives this design: **2,712 nodes** after the `fold_key` code-merge, but
**~285/312/330 recurring epithet nodes per canticle** — too many for one grouping call, so both
Step-3 decision gates FAILED.

## Output

`05-registry/<canticle>.txt`, committed. One process over all three canticles; canonical labels
decided **globally** so a cross-canticle figure shares one label. Add `load_registry(canticle)` to
`dante_analyze/checkpoint.py` once this format is frozen.

```
# Registry — inferno

## Virgilio
- type: individual
- labels: Virgilio
- surfaces: tu (412), elli (88), maestro (12), ...

## Cammilla, Eurialo, Turno, Niso
- type: set
- members: Cammilla | Eurialo | Turno | Niso
```

(`set` is a structural kind orthogonal to the five node types; members reference other nodes'
canonical labels. Under option (A) below, add a `grouped: no` flag to ungrouped epithet nodes.)

## Code-merge stage (pure code — gates confirm it works)

Collect distinct labels (`load_tags`) → resolve sets (`split_set`) → group by `fold_key`, canonical
= most frequent original spelling → alias surfaces by joining `load_tags` × `number_scene` meta into
a per-node surface inventory with counts (full tag-level provenance NOT serialized — recomputable by
the same join). This deterministically collapses 2,923 distinct labels → 2,712 nodes.

## LLM residual stage (`gemma4:31b-it-qat`, CoT on, via `call_llm`, `tags.py` as template)

### Node typing  [tractable as planned — ~136 calls]

Closed vocabulary `individual | generic | class | hypothetical-simile | non-person`; batches of ~20
nodes, reply `n. <label> = <type>`; check: every batch label typed exactly once, type in vocabulary,
label echoed verbatim; pinpointed retry (ARCH §5).

### Epithet grouping  — ⚠ OPEN DECISION (pick before building)

The gate failed here: the per-canticle candidate list (~300) cannot fit one LLM call.

- **(A) v1 skip** — every epithet node stays its own node, flagged (e.g. `grouped: no`). Ships a
  working registry now; consolidation is a later pass. Cross-unit reconciliation is inherently the
  hard part (ARCH §11), and the structure check **cannot police a wrong grouping** — so a flagged
  singleton is safer than an unverifiable merge. **Recommended for v1.**
- **(B) batched grouping** — split each canticle's ~300-candidate list into batches, one call each;
  the per-batch check (every proposed member ∈ that batch, no label in two groups) still holds. Costs
  more design + tokens and risks cross-batch splits a single call would have caught — without buying
  a check that can verify correctness.

## Structural check (at write time, re-runnable)

Every distinct 04-tags label assigned to exactly one node's `labels:` (`(unknown)` exempt); every
member resolves to a node; every type in vocabulary; canonical heading is one of its group's raw labels.

## Wiring & verification (registry-specific)

- `05-registry/Makefile`: `include ../model.mk`; `all:` runs `registry.py` with `$(MODEL)`; a
  `measure:` target for `measure.py`.
- `cli.py`: `dante-analyze registry show <canticle>` (per-canticle path, special-cased like scenes).
- On completion: rename this `PLAN.md` → `README.md`; add the row to root `PLAN.md` File structure.

```bash
uv run 05-registry/registry.py inferno purgatorio paradiso -m $(MODEL)
uv run dante-analyze registry show inferno
# spot-check: every distinct 04-tags label appears in exactly one node's labels: line
```
