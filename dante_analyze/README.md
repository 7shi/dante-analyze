# dante_analyze

Internal shared library for this repo's analysis passes (`01-scenes/` … `08-kg/`): the
project-root path anchors, the `call_llm` LLM gateway, tag/quote-span/label utilities, the
`## Scene` checkpoint I/O, and the output loaders the passes import. Per-pass design lives in each
numbered subdirectory's `README.md`; the conventions every pass shares are in `ARCHITECTURE.md`.

Functionality intended for use **from outside the project** is published in two parallel forms over
the same committed outputs: the read-only **CLI** (`show`) and the **Public API** (the `load_*`
loaders + path constants). The rest of the package — the `call_llm` gateway, `number_scene` and the
mark/label utilities, the prompt builders, the checkpoint *writers* — is internal pipeline plumbing
the passes use and is **not** part of the public surface (see the subdir `README.md`s and
`ARCHITECTURE.md`).

## CLI

```
dante-analyze <layer> show <canticle> [<canto> | <part>]
```

Prints the committed output for the unit to stdout, exiting 1 with a message to stderr if it is
absent. `scenes` is rendered to a readable digest (canto title + per-scene headings/summaries); the
rest print the committed file verbatim.

| `<layer>`   | arguments            | prints |
|-------------|----------------------|--------|
| `scenes`    | `<canticle> <canto>` | rendered scene digest for the canto (from `01-scenes/<canticle>/NN.json`) |
| `reading`   | `<canticle> <canto>` | free prose reading (`03-reading/<canticle>/NN.txt`) |
| `tags`      | `<canticle> <canto>` | identity-first `n. Name` table (`04-tags/<canticle>/NN.txt`) |
| `registry`  | `<canticle>`         | canonical node table (`05-registry/<canticle>.txt`) |
| `speech`    | `<canticle> <canto>` | speaker per quote span (`06-speech/<canticle>/NN.txt`) |
| `relations` | `<canticle> <canto>` | subject–predicate–object edges (`07-relations/<canticle>/NN.txt`) |
| `kg`        | `<canticle> [<part>]`| assembled graph JSONL; `<part>` = `nodes` / `edges` / `speech` (default `edges`) (`08-kg/<canticle>-<part>.jsonl`) |

`<canticle>` is `inferno` / `purgatorio` / `paradiso`; `<canto>` is an integer. `registry` and `kg`
are work-wide, so they take no canto (`kg` instead takes an optional `<part>`, default `edges`).

**Examples**

```bash
dante-analyze scenes    show inferno 1
dante-analyze tags      show paradiso 33
dante-analyze registry  show inferno
dante-analyze relations show inferno 1
dante-analyze kg        show inferno edges
```

## Public API

The same committed outputs, as structured data. All names below are importable from the top-level
package (`from dante_analyze import load_relations, RELATIONS_DIR`). Each `load_*` exits the process
with a message to stderr if its file is absent.

### Output loaders

```python
load_scenes(canticle, canto)    -> (canto_title: str, [(start, end, scene_name), …])
load_readings(canticle, canto)  -> {(start, end): prose}
load_tags(canticle, canto)      -> {(start, end): {tag_no: name}}
load_registry(canticle)         -> {canonical: {type, labels, surfaces, members, grouped}}
load_speech(canticle, canto)    -> [{quote_id, start, end, speaker, signal, flags}, …]   # file order
load_relations(canticle, canto) -> [{subj, predicate, obj, frame, start, end}, …]        # file order
load_kg(canticle)               -> {nodes: […], edges: […], speech: […]}                  # 08-kg graph
```

`canticle` is `inferno` / `purgatorio` / `paradiso`; `canto` is an integer (`load_registry` and
`load_kg` are work-wide per canticle). The cited `[n]` in a `load_relations` edge are the same
per-scene tag numbers `load_tags` keys on, so `subj`/`obj` join through `load_tags` to a name (and
onward to a registry node); the edge's `start..end` falls inside exactly one scene. `load_kg` returns
that join already performed (08-kg, Step 4) — one call for the whole graph:

- `nodes`:  `{id, type, members}` (members `None` unless a set node) — the registry distilled.
- `edges`:  `{canto, scene, subj, predicate, obj, frame, lines, asserter}`; `subj`/`obj` are
  `{tag, name, node}` (`node` `None` if the label didn't resolve).
- `speech`: `{canto, quote_id, lines, speaker, signal, flags}` — the `06-speech` spans.

### Helpers

```python
raw_to_canonical(canticle)      -> {fold_key(spelling): canonical}   # name -> registry node join
```

The total name→node join `06-speech` and `08-kg` both canonicalize `04-tags` labels through:
`raw_to_canonical(canticle)[fold_key(norm_label(name))]` → the registry canonical heading (shared in
the package per ARCHITECTURE §16).

### Path constants

```python
SCENE_DIR  MARKUP_DIR  READING_DIR  TAGS_DIR  REGISTRY_DIR  SPEECH_DIR  RELATIONS_DIR  KG_DIR
```

Project-root output directories, for locating the committed files directly. Per-canto files are
`<DIR>/<canticle>/NN.txt` (registry is per-canticle: `REGISTRY_DIR/<canticle>.txt`; the KG is
per-canticle JSONL: `KG_DIR/<canticle>-{nodes,edges,speech}.jsonl`).
