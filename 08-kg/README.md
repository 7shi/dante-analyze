# 08-kg — knowledge-graph assembly (KG Step 4)

The last step of the KG ladder. It **joins** the committed upstream outputs into the assembled
graph — **pure code, no LLM**. Every input is read through the `dante_analyze` `load_*` public API;
no text is re-interpreted here. The graph is the precursor the translation context lock
(`dante-dravidian`) consumes.

This pass exists because the earlier passes deliberately kept *understanding* and *extraction*
apart (ARCHITECTURE §14): `03-reading`/`04-tags` resolved WHO, `05-registry` made the nodes,
`06-speech` found the speakers, `07-relations` emitted the who-does-what edges citing `[n]` tags.
None of those is the graph; they are referent-resolved material with the join deferred. Step 4 is
that deferred join, and it is total by construction — the upstream structural checks (tag numbers
stay aligned, every cited `[n]` exists, every edge's line range sits in one scene) are exactly what
let code resolve each edge end to a node mechanically.

## What it does

Per canticle, per canto, over `load_relations(canticle, canto)`:

- **Resolve each edge end to a node.** An edge's `lines a-b` falls inside exactly one `04-tags`
  scene (scenes partition the canto), so find that scene `(s, e)`, map the cited `[subj]`/`[obj]`
  through `load_tags(...)[(s, e)]` → a name, and canonicalize the name through the registry
  (`raw_to_canonical` → `fold_key` → the canonical heading) → the graph **node**.
- **Recover the asserter.** For `reported` / `prophecy` / `simile` edges, the asserter is the
  speaker of the **innermost** `06-speech` quote span containing the edge's line range
  (`load_speech`). `literal` edges are narrated and have no asserter (so `null`); an `(unattributed)`
  container also yields `null`.
- **Merge the speech edges** (speaker → quote span) alongside the relation edges.

Then a structural check runs; output is written only when it passes.

## Inputs / outputs

```
Input:  07-relations/<canticle>/NN.txt  (edges)      06-speech/<canticle>/NN.txt (speaker per span)
        04-tags/<canticle>/NN.txt       (per-scene [n] -> name)
        05-registry/<canticle>.txt      (canonical node table)
Output: 08-kg/<canticle>/NN.json        (edges + speech_edges, per canto)
        08-kg/<canticle>.nodes.json     (registry distilled to graph nodes, per canticle)
```

Granularity is split on purpose: edges/speech are **per canto** (matching `07-relations`/`06-speech`
so a downstream per-canto translation pass integrates cleanly), the node table is **per canticle**
(matching `05-registry`). Read them with `load_kg(canticle, canto)` and `load_kg_nodes(canticle)`,
or `dante-analyze kg show <canticle> <canto>`.

### `<canticle>.nodes.json` — the node table

`id` is the registry canonical heading; `type` is the node type; `members` is the member list for a
set node, else `null` (surfaces/labels are dropped — the graph references nodes by `id`).

```json
{ "canticle": "inferno",
  "nodes": [
    { "id": "Dante",    "type": "individual", "members": null },
    { "id": "Virgilio", "type": "individual", "members": null } ] }
```

### `<canticle>/NN.json` — resolved edges + speech edges

```json
{ "canticle": "inferno", "canto": 1,
  "edges": [
    { "scene": [49, 60],
      "subj": {"tag": 2, "name": "la lupa", "node": "la lupa"},
      "predicate": "punishes",
      "obj":  {"tag": 3, "name": "Dante", "node": "Dante"},
      "frame": "literal", "lines": [52, 52],
      "asserter": null },
    { "scene": [67, 75],
      "subj": {"tag": 8, "name": "Virgilio", "node": "Virgilio"},
      "predicate": "relates-to",
      "obj":  {"tag": 9, "name": "Augusto", "node": "Augusto"},
      "frame": "reported", "lines": [71, 71],
      "asserter": "Virgilio" } ],
  "speech_edges": [
    { "quote_id": "1:67", "lines": [67, 78], "speaker": "Virgilio",
      "signal": "strong", "flags": ["cross-scene"] } ] }
```

- `subj`/`obj`: `tag` is the cited `[n]`; `name` is the `04-tags` label; `node` is the resolved
  registry canonical, or `null` when the label doesn't resolve (see below).
- `asserter`: the recovered speaker for asserting frames, else `null`.
- `speech_edges`: the `06-speech` spans verbatim (speaker → quote span).

## The structural check

Mirrors `06-speech`'s fail-loud gate; output is written only on a clean canto.

- **Geometry (fatal, aborts the run):** every edge's line range lies in **exactly one** scene, and
  every cited `[n]` exists in that scene's tag set. These are the invariants the upstream checks
  promised; a violation is a real desync, so the run stops.
- **Name→node resolution (tallied, not fatal):** an edge end whose label doesn't canonicalize to a
  node is written with `node: null` and counted to stderr. Per the project ethos (confirm the
  pipeline's accuracy, don't patch by hand) the residual count is itself measurement, not a defect
  to fix. In the committed run every such end is a `(unknown)` label — the referent the model never
  identified, which the registry rightly dropped — so no un-registered surface leaks through.
- **Asserter join:** 0-or-1 by construction (innermost containing span); never fatal.

## Measured result (committed run)

| canticle   | nodes | edges |
|------------|------:|------:|
| inferno    | 1045  | 2142  |
| purgatorio |  936  | 2010  |
| paradiso   | 1050  | 1604  |

Geometry: **0 failures** across all 100 cantos — every edge resolved to exactly one scene, every
cited tag present. Name→node: **18 unresolved edge ends total** (inferno 2, purgatorio 10, paradiso
6), all of them `(unknown)` labels.

## Run

```bash
make -C 08-kg                              # build all three canticles
uv run dante-analyze kg show inferno 1     # inspect a canto
```

**Parallel-safe** (ARCHITECTURE §15): per-canto JSON outputs, read-only committed inputs, no shared
writable state — safe to fan out per canticle; on the local default it is fast enough to not bother.

## Notes

- `raw_to_canonical` (name → canonical via `fold_key`) lives in `dante_analyze/checkpoint.py`, shared
  with `06-speech` — reused code belongs in the package, not in a pass script (ARCHITECTURE §16).
