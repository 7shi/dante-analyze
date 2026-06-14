# dante_analyze

Internal shared library for this repo's analysis passes (`01-scenes/` … `07-relations/`): the
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
dante-analyze <layer> show <canticle> [<canto>]
```

Prints a committed output file to stdout; exits 1 with a message to stderr if it is absent.

| `<layer>`   | arguments            | prints |
|-------------|----------------------|--------|
| `scenes`    | `<canticle> <canto>` | scene breakdown for the canto (`01-scenes/<canticle>/NN.json`) |
| `reading`   | `<canticle> <canto>` | free prose reading (`03-reading/<canticle>/NN.txt`) |
| `tags`      | `<canticle> <canto>` | identity-first `n. Name` table (`04-tags/<canticle>/NN.txt`) |
| `registry`  | `<canticle>`         | canonical node table (`05-registry/<canticle>.txt`) |
| `speech`    | `<canticle> <canto>` | speaker per quote span (`06-speech/<canticle>/NN.txt`) |
| `relations` | `<canticle> <canto>` | subject–predicate–object edges (`07-relations/<canticle>/NN.txt`) |

`<canticle>` is `inferno` / `purgatorio` / `paradiso`; `<canto>` is an integer (`registry` is
work-wide, so it takes no canto).

**Examples**

```bash
dante-analyze scenes    show inferno 1
dante-analyze tags      show paradiso 33
dante-analyze registry  show inferno
dante-analyze relations show inferno 1
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
```

`canticle` is `inferno` / `purgatorio` / `paradiso`; `canto` is an integer (`load_registry` is
work-wide). The cited `[n]` in a `load_relations` edge are the same per-scene tag numbers
`load_tags` keys on, so `subj`/`obj` join through `load_tags` to a name (and onward to a registry
node); the edge's `start..end` falls inside exactly one scene.

### Path constants

```python
SCENE_DIR  MARKUP_DIR  READING_DIR  TAGS_DIR  REGISTRY_DIR  SPEECH_DIR  RELATIONS_DIR
```

Project-root output directories, for locating the committed files directly. Per-canto files are
`<DIR>/<canticle>/NN.txt` (registry is per-canticle: `REGISTRY_DIR/<canticle>.txt`).
