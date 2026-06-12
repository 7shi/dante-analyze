"""Per-canto checkpoint file I/O: read, navigate, and write the `## Scene s-e` block
format used by every analysis pass, plus higher-level loaders `load_readings` and
`load_tags`."""
import re
import sys

from ._paths import READING_DIR, TAGS_DIR

# A tags `n. Name` line (the authoritative resolution; line n = tag [n]).
TAGS_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")

SCENE_HEAD_RE = re.compile(r"^## Scene (\d+)-(\d+):")
RECAP_HEAD = "# recap"


def out_path(out_dir, canticle, canto):
    """The committed per-canto checkpoint under `out_dir`: <out_dir>/<canticle>/NN.txt."""
    return out_dir / canticle / f"{canto:02d}.txt"


def done_scene_ends(path):
    """End-line of every `## Scene s-e` block already written — used to skip
    finished scenes on resume (the file is the checkpoint)."""
    ends = set()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            m = SCENE_HEAD_RE.match(raw)
            if m:
                ends.add(int(m.group(2)))
    return ends


def read_recap(path):
    """The `# recap` block of a finished canto file, for carry-forward."""
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, raw in enumerate(lines):
        if raw.strip() == RECAP_HEAD:
            return "\n".join(l for l in lines[i + 1:] if l.strip())
    return ""


def iter_scene_blocks(path):
    """Yield (start, end, block_text) for each `## Scene s-e` block in a canto file,
    excluding the trailing `# recap`. `block_text` is the whole block (header line
    included), stripped; a caller wanting only the body drops the first line."""
    if not path.exists():
        return
    body = path.read_text(encoding="utf-8").split(f"{RECAP_HEAD}\n", 1)[0]
    for block in re.split(r"(?=^## Scene )", body, flags=re.M):
        m = SCENE_HEAD_RE.match(block)
        if m:
            yield int(m.group(1)), int(m.group(2)), block.strip()


def scene_bodies(path):
    """{(start, end): body} for each `## Scene s-e` block, body = the block minus its
    header, stripped (empty string if the scene was written with no reading)."""
    out = {}
    for s, e, block in iter_scene_blocks(path):
        body = block.split("\n", 1)[1].strip() if "\n" in block else ""
        out[(s, e)] = body
    return out


def complete_scene_ends(path):
    """End-line of every scene with a NON-EMPTY body — the scenes actually finished.
    Unlike done_scene_ends (header-only), a scene written with a blank body is NOT
    counted, so a resumed run regenerates it instead of silently skipping a hole that
    would later starve digest/tags (the file is the checkpoint, ARCHITECTURE §9)."""
    return {e for (_s, e), body in scene_bodies(path).items() if body}


def restore_blocks(path):
    """The normalized `## Scene` block strings already in a canto file, so a resumed
    run can rewrite the file with finished scenes intact."""
    return [f"{block}\n" for _, _, block in iter_scene_blocks(path)]


def render_scene_block(s, e, scene_name, body):
    """One `## Scene s-e: name` block wrapping an arbitrary `body` (prose for
    reading.py; bullets + resolution for bullets.py)."""
    return f"## Scene {s}-{e}: {scene_name}\n{body}\n"


def append_canto(path, canto, canto_title, blocks, recap=None):
    """(Re)write the whole canto file from `blocks` (+ optional recap). Rewriting
    the file each scene keeps the header/recap consistent and the file length an
    honest checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [f"# Canto {canto:02d} — {canto_title}\n", *blocks]
    if recap:
        parts.append(f"{RECAP_HEAD}\n{recap}\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def load_readings(canticle, canto):
    """{(start, end): prose} for a canto from 03-reading/<canticle>/NN.txt, or exit if the
    file is absent. The prose is the scene block minus its `## Scene` header. tags.py
    replays this committed reading as the assistant's reasoning turn."""
    path = out_path(READING_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: reading not found: {path} (run 03-reading/reading.py first)", file=sys.stderr)
        sys.exit(1)
    return scene_bodies(path)


def load_tags(canticle, canto):
    """{(start, end): {tag_no: name}} for a canto from 04-tags/<canticle>/NN.txt, or exit if the
    file is absent — the authoritative per-scene referent table the downstream consumes. Each
    `n. Name` line becomes {n: name}, the labels exactly as committed (tags.py already applied
    `fix_elision` at generation time — no post-run verifier)."""
    path = out_path(TAGS_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: tags not found: {path} (run 04-tags/tags.py first)", file=sys.stderr)
        sys.exit(1)
    out = {}
    for (s, e), body in scene_bodies(path).items():
        res = {}
        for line in body.splitlines():
            m = TAGS_LINE_RE.match(line)
            if m:
                res[int(m.group(1))] = m.group(2)
        out[(s, e)] = res
    return out
