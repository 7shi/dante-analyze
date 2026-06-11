# dante_analyze

Analysis pipeline library for Dante's *Divina Commedia*. Provides shared I/O,
LLM call infrastructure, text processing utilities, and a read-only query CLI
over the committed analysis outputs.

---

## CLI

```
dante-analyze <layer> show <canticle> <canto>
```

Prints the committed checkpoint file for the given layer, canticle, and canto to stdout.

| Parameter   | Description                                         |
|-------------|-----------------------------------------------------|
| `layer`     | `scenes` / `reading` / `bullets` / `tags`           |
| `canticle`  | e.g. `inferno`, `purgatorio`, `paradiso`            |
| `canto`     | integer canto number                                |

**Examples**

```bash
dante-analyze scenes  show inferno 1
dante-analyze reading show inferno 1
dante-analyze bullets show purgatorio 10
dante-analyze tags    show paradiso 33
```

Exits with status 1 and an error message to stderr if the file does not exist.

---

## Directory layout

```
01-scenes/   <canticle>/NN.json    scene JSON (committed)
02-markup/   <canticle>/NN-4.txt   markup lines (gitignored; input to passes)
03-reading/  <canticle>/NN.txt     reading pass output
04-bullets/  <canticle>/NN.txt     bullets pass output
05-tags/     <canticle>/NN.txt     tags pass output
```

Path constants are exported from `dante_analyze`:
`SCENE_DIR`, `MARKUP_DIR`, `READING_DIR`, `BULLETS_DIR`, `TAGS_DIR`.

---

## Public API

### Corpus input readers (`corpus.py`)

```python
read_markup(canticle, canto) -> list[str]
```
Loads the `NN-4.txt` marked lines for a canto. Exits with an error message if the
file is absent (caller must run `02-markup/markup.py` first).

```python
available_cantos(canticle) -> list[int]
```
Returns canto numbers that have a finished `NN-4.txt` markup file, sorted.

```python
load_scenes(canticle, canto) -> (canto_title: str, scenes: list[tuple[int, int, str]])
```
Loads scene boundaries from `01-scenes/<canticle>/NN.json`.
Each scene tuple is `(start_line, end_line, scene_name)`.

---

### Checkpoint I/O (`checkpoint.py`)

Checkpoint files use a shared block format:

```
# Canto NN — <title>

## Scene <s>-<e>: <scene_name>
<body>

# recap
<recap text>
```

```python
out_path(out_dir, canticle, canto) -> Path
```
Returns `out_dir / canticle / NN.txt`.

```python
done_scene_ends(path) -> set[int]
```
End-lines of every `## Scene s-e` block header already written (used to skip
finished scenes on resume).

```python
complete_scene_ends(path) -> set[int]
```
Like `done_scene_ends`, but only counts scenes whose body is non-empty.

```python
read_recap(path) -> str
```
Returns the `# recap` block of a finished canto file (for carry-forward to the
next canto). Returns `""` if absent.

```python
iter_scene_blocks(path) -> Iterator[tuple[int, int, str]]
```
Yields `(start, end, block_text)` for each scene block. `block_text` includes the
header line and is stripped; the `# recap` section is excluded.

```python
scene_bodies(path) -> dict[tuple[int, int], str]
```
Returns `{(start, end): body}` — the block text with the `## Scene` header removed.

```python
restore_blocks(path) -> list[str]
```
Normalized scene block strings already in the file, for rewriting on resume.

```python
render_scene_block(s, e, scene_name, body) -> str
```
Formats one `## Scene s-e: name\n<body>\n` block string.

```python
append_canto(path, canto, canto_title, blocks, recap=None)
```
(Re)writes the entire canto file from `blocks` plus an optional recap section.
Creates parent directories as needed.

```python
load_readings(canticle, canto) -> dict[tuple[int, int], str]
```
Loads `{(start, end): prose}` from `03-reading/<canticle>/NN.txt`.
Exits with an error if the file is absent.

```python
load_tags(canticle, canto) -> dict[tuple[int, int], dict[int, str]]
```
Loads `{(start, end): {tag_no: name}}` from `05-tags/<canticle>/NN.txt`.
Each `n. Name` line becomes `{n: name}`. Exits with an error if the file is absent.

```python
TAGS_LINE_RE  # re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
```

---

### Text processing (`marks.py`)

```python
number_scene(lines, s, e) -> (tagged_text: str, k: int, meta: dict[int, tuple[str, str]])
```
Splices a scene-local numeric index into every mark in lines `s..e`.
- `tagged_text`: numbered lines joined as `"12 …\n13 …"`.
- `k`: total tag count.
- `meta`: `{tag_no: (kind, surface)}` — `kind` is `"pron"` for `[..]` / `[+..]`
  or `"name"` for `{..}`; `surface` is the marked text (leading `+` stripped).

```python
parse_bullets(text) -> list[str]
```
Extracts bullet bodies from lines beginning with `- ` or `* `.

```python
unbrace(text) -> str
```
Normalizes model reply brackets: converts `{n}` → `[n]` and removes backtick
wrapping. Apply at the reply boundary so normalized text enters conversation history.

```python
fix_elision(label) -> str
```
Repairs the tags-pass de-elision over-correction: elidable Italian determiners
(`la`, `lo`, `una`, `dello`, `della`, …) that were left un-elided before a vowel
are restored to the contracted apostrophe form (`l'altra`, `nell'uccello`).

```python
ELIDE_RE  # compiled pattern matching the elidable determiners
```

---

### LLM boundary (`llm.py`)

```python
MAX_LENGTH = 10000   # per-reply character cap
LLM_RETRIES = 3      # retries on repetition / cap hit / empty reply
```

```python
call_llm(messages, model, retries=LLM_RETRIES, max_length=MAX_LENGTH,
         include_thoughts=False) -> Response
```
Wrapper around `llm7shi.compat.generate_with_schema`. Regenerates up to `retries`
times if the reply shows repetition, hits `max_length`, or is empty. Chain-of-thought
is off by default; pass `include_thoughts=True` for the reading pass where precision
matters (thinking stays internal; `resp.text` is the clean prose).

```python
step_sep(title)
```
Prints `\n--- title ---` as a progress separator.

---

### Prompt builder (`prompts.py`)

```python
build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, prior, recap) -> str
```
Constructs the Turn-1 user message for the free-interpretation reasoning step shared
by `reading.py`, `bullets.py`, and `tags.py`. Includes optional carry-forward context
(`recap` from the previous canto, `prior` reading of earlier scenes in this canto).
`tagged` is the numbered scene text produced by `number_scene`.
