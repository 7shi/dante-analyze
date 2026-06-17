"""Per-canto checkpoint file I/O: read, navigate, and write the `## Scene s-e` block
format used by every analysis pass, plus higher-level loaders `load_readings` and
`load_tags`."""
import json
import re
import sys

from ._paths import (
    READING_DIR, TAGS_DIR, REGISTRY_DIR, SPEECH_DIR, RELATIONS_DIR, KG_DIR, LOCATION_DIR,
    TOPOGRAPHY_DIR, PRESENCE_DIR, ADDRESSEE_DIR, COHORT_DIR, LOCK_DIR,
)
from .labels import fold_key

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
    would later starve digest/tags (the file is the checkpoint)."""
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


# A registry `## <canonical>` node heading and a `- key: value` field line.
REGISTRY_HEAD_RE = re.compile(r"^##\s+(.*\S)\s*$")
REGISTRY_FIELD_RE = re.compile(r"^-\s+(\w+):\s*(.*)$")


def load_registry(canticle):
    """{canonical: node} for a canticle from 05-registry/<canticle>.txt, or exit if absent.

    `node` is a dict with the parsed fields: `type` (str), and either `members` (list, for a
    `set` node) or `labels` (list of raw spellings) + `surfaces` (list of (form, count)); the
    `grouped: no` flag becomes `grouped=False`. Built by 05-registry/registry.py; the canonical
    heading is the node's global label, surfaces/labels are this canticle's (registry.py)."""
    path = REGISTRY_DIR / f"{canticle}.txt"
    if not path.exists():
        print(f"Error: registry not found: {path} (run 05-registry/registry.py first)",
              file=sys.stderr)
        sys.exit(1)
    out = {}
    node = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        h = REGISTRY_HEAD_RE.match(raw)
        if h:
            node = {"type": None, "labels": [], "surfaces": [], "members": [], "grouped": True}
            out[h.group(1)] = node
            continue
        if node is None:
            continue
        f = REGISTRY_FIELD_RE.match(raw)
        if not f:
            continue
        key, val = f.group(1), f.group(2).strip()
        if key == "type":
            node["type"] = val
        elif key == "members":
            node["members"] = [m.strip() for m in val.split("|") if m.strip()]
        elif key == "labels":
            node["labels"] = [m.strip() for m in val.split("|") if m.strip()]
        elif key == "surfaces":
            for item in (s.strip() for s in val.split(",") if s.strip()):
                m = re.match(r"^(.*\S)\s+\((\d+)\)$", item)
                if m:
                    node["surfaces"].append((m.group(1), int(m.group(2))))
        elif key == "grouped":
            node["grouped"] = val.lower() != "no"
    return out


def raw_to_canonical(canticle):
    """{fold_key(spelling): canonical} from the committed registry — the total join a pass
    canonicalizes 04-tags labels through (06-speech and 08-kg both go this way).
    The registry built its `labels` from norm_label'd spellings keyed by fold_key, so
    fold_key(norm_label(raw)) for every non-(unknown) label hits this map. A set node carries no
    `labels:`; its heading itself is the surface that occurred."""
    m = {}
    for canonical, node in load_registry(canticle).items():
        for sp in (node["labels"] or [canonical]):
            m[fold_key(sp)] = canonical
    return m


# A speech span line: "- <quote_id> lines <s>-<e> | speaker: <name> | signal: <sig> | flags: <flags>"
SPEECH_LINE_RE = re.compile(
    r"^-\s+(?P<qid>\S+)\s+lines\s+(?P<s>\d+)-(?P<e>\d+)\s*\|\s*"
    r"speaker:\s*(?P<speaker>.*\S)\s*\|\s*signal:\s*(?P<signal>\w+)\s*\|\s*"
    r"flags:\s*(?P<flags>.*\S)\s*$"
)


def load_speech(canticle, canto):
    """[span, …] in file order for a canto from 06-speech/<canticle>/NN.txt, or exit if absent.

    Each span is a dict {quote_id, start, end, speaker, signal, flags}; `flags` is a list (empty
    when the file's flags field is `-`). Built by 06-speech/speech.py — the speaker is a registry
    canonical label (or `(unattributed)`)."""
    path = out_path(SPEECH_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: speech not found: {path} (run 06-speech/speech.py first)", file=sys.stderr)
        sys.exit(1)
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = SPEECH_LINE_RE.match(raw)
        if not m:
            continue
        flags = m.group("flags").strip()
        out.append({
            "quote_id": m.group("qid"),
            "start": int(m.group("s")),
            "end": int(m.group("e")),
            "speaker": m.group("speaker").strip(),
            "signal": m.group("signal"),
            "flags": [] if flags == "-" else [f.strip() for f in flags.split(",") if f.strip()],
        })
    return out


# A relations edge line: "- [<subj>] <predicate> [<obj>] | frame: <frame> | lines <s>-<e>".
RELATIONS_LINE_RE = re.compile(
    r"^-\s*\[(?P<subj>\d+)\]\s+(?P<pred>\S+)\s+\[(?P<obj>\d+)\]\s*\|\s*"
    r"frame:\s*(?P<frame>\w+)\s*\|\s*lines\s+(?P<s>\d+)-(?P<e>\d+)\s*$"
)


def load_relations(canticle, canto):
    """[edge, …] in file order for a canto from 07-relations/<canticle>/NN.txt, or exit if absent.

    Each edge is a dict {subj, predicate, obj, frame, start, end} (subj/obj/start/end ints); the
    cited [subj]/[obj] are the SAME per-scene `number_scene` tag numbers 04-tags resolved against,
    so Step 4 joins each through load_tags. The list is flat (no scene key): the edge's line range
    falls inside exactly one scene because scenes partition the canto, so the scene is recoverable.
    Built by 07-relations/relations.py."""
    path = out_path(RELATIONS_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: relations not found: {path} (run 07-relations/relations.py first)",
              file=sys.stderr)
        sys.exit(1)
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = RELATIONS_LINE_RE.match(raw)
        if not m:
            continue
        out.append({
            "subj": int(m.group("subj")),
            "predicate": m.group("pred"),
            "obj": int(m.group("obj")),
            "frame": m.group("frame"),
            "start": int(m.group("s")),
            "end": int(m.group("e")),
        })
    return out


def _load_kg_jsonl(canticle, part):
    """[record, …] from a per-canticle 08-kg/<canticle>/<part>.jsonl, or exit if absent.

    The assembled graph is JSONL — one record per line, all cantos aggregated. Built by
    08-kg/assembly.py (`make -C 08-kg`); see 08-kg/README.md."""
    path = KG_DIR / canticle / f"{part}.jsonl"
    if not path.exists():
        print(f"Error: kg {part} not found: {path} (run 08-kg/assembly.py first)", file=sys.stderr)
        sys.exit(1)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# A location line: "- it: <source term> | en: <english gloss> | basis: <s>[-<e>]".
LOCATION_LINE_RE = re.compile(
    r"^-\s*it:\s*(?P<it>.*?)\s*\|\s*en:\s*(?P<en>.*?)\s*\|\s*"
    r"basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)


def load_locations(canticle, canto):
    """{(start, end): [loc, …]} for a canto from 09-location/<canticle>/NN.txt, or exit if absent.

    Each loc is a dict {it, en, basis_start, basis_end}: `it` is the source-text place term (the
    surface 10-topography folds; `-` when the setting is purely carried), `en` an English gloss,
    and `basis_start`/`basis_end` the source line range that supports the setting (within the
    scene). The first loc of a scene is the primary current setting. Built by 09-location/location.py."""
    path = out_path(LOCATION_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: location not found: {path} (run 09-location/location.py first)",
              file=sys.stderr)
        sys.exit(1)
    out = {}
    for (s, e), body in scene_bodies(path).items():
        locs = []
        for line in body.splitlines():
            m = LOCATION_LINE_RE.match(line)
            if m:
                bs = int(m.group("bs"))
                locs.append({
                    "it": m.group("it"),
                    "en": m.group("en"),
                    "basis_start": bs,
                    "basis_end": int(m.group("be")) if m.group("be") else bs,
                })
        out[(s, e)] = locs
    return out


# A presence line: "- who: <name> | status: present|mentioned | basis: s[-e]". The `-e` is optional
# (a one-line basis may be written `basis: 17`); 11-presence renders the two-number form.
PRESENCE_LINE_RE = re.compile(
    r"^-\s*who:\s*(?P<who>.*?)\s*\|\s*status:\s*(?P<status>present|mentioned)\s*\|\s*"
    r"basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)


def load_presence(canticle, canto):
    """{(start, end): [fig, …]} for a canto from 11-presence/<canticle>/NN.txt, or exit if absent.

    Each fig is a dict {who, status, basis_start, basis_end}: `who` is the canonical figure label
    (source spelling, matching the KG nodes), `status` is `present` (bodily in the scene) or
    `mentioned` (named but not present), and `basis_start`/`basis_end` the source line range
    supporting the call (within the scene). A scene that names no person figure carries an empty
    list. Built by 11-presence/presence.py."""
    path = out_path(PRESENCE_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: presence not found: {path} (run 11-presence/presence.py first)",
              file=sys.stderr)
        sys.exit(1)
    out = {}
    for (s, e), body in scene_bodies(path).items():
        figs = []
        for line in body.splitlines():
            m = PRESENCE_LINE_RE.match(line)
            if m:
                bs = int(m.group("bs"))
                figs.append({
                    "who": m.group("who"),
                    "status": m.group("status"),
                    "basis_start": bs,
                    "basis_end": int(m.group("be")) if m.group("be") else bs,
                })
        out[(s, e)] = figs
    return out


# An addressee line: "- <quote_id> lines <s>-<e> | speaker: <name> | addressee: <name>|(none) |
# source: code|llm|none | basis: bs[-be]". One per ATTRIBUTED 06-speech span. The `-be` is optional.
ADDRESSEE_LINE_RE = re.compile(
    r"^-\s+(?P<qid>\S+)\s+lines\s+(?P<s>\d+)-(?P<e>\d+)\s*\|\s*"
    r"speaker:\s*(?P<speaker>.*?)\s*\|\s*addressee:\s*(?P<addr>.*?)\s*\|\s*"
    r"source:\s*(?P<src>\w+)\s*\|\s*basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)


def load_addressee(canticle, canto):
    """{(start, end): [span, …]} for a canto from 12-addressee/<canticle>/NN.txt, or exit if absent.

    Keyed by the SCENE that contains each span's start line. Each span is a dict {quote_id, start,
    end, speaker, addressee, source, basis_start, basis_end}: `speaker` is the canonical figure the
    06-speech span is attributed to, `addressee` the canonical figure it is directed at (or `(none)`
    when no other figure is present), `source` is `code` (one present candidate), `llm` (chosen from
    several), or `none` (no candidate), and `basis_start`/`basis_end` the supporting source line
    range. Unattributed spans carry no line. Built by 12-addressee/addressee.py."""
    path = out_path(ADDRESSEE_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: addressee not found: {path} (run 12-addressee/addressee.py first)",
              file=sys.stderr)
        sys.exit(1)
    out = {}
    for (s, e), body in scene_bodies(path).items():
        spans = []
        for line in body.splitlines():
            m = ADDRESSEE_LINE_RE.match(line)
            if m:
                bs = int(m.group("bs"))
                spans.append({
                    "quote_id": m.group("qid"),
                    "start": int(m.group("s")),
                    "end": int(m.group("e")),
                    "speaker": m.group("speaker"),
                    "addressee": m.group("addr"),
                    "source": m.group("src"),
                    "basis_start": bs,
                    "basis_end": int(m.group("be")) if m.group("be") else bs,
                })
        out[(s, e)] = spans
    return out


# A cohort line: "- cohort: <name>|(none) | source: code|llm|none | basis: bs[-be]". One per
# soul-class a scene's present cast resolves to (a scene with none carries a `#` marker).
COHORT_LINE_RE = re.compile(
    r"^-\s*cohort:\s*(?P<cohort>.*?)\s*\|\s*source:\s*(?P<src>\w+)\s*\|\s*"
    r"basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)


def load_cohort(canticle, canto):
    """{(start, end): [cohort, …]} for a canto from 13-cohort/<canticle>/NN.txt, or exit if absent.

    Each cohort is a dict {cohort, source, basis_start, basis_end}: `cohort` is the canonical
    soul-class label (source spelling, a 05-registry `class`/`generic` node), `source` is `code`
    (one present candidate), `llm` (chosen from several), or `none` (no present soul-class), and
    `basis_start`/`basis_end` the supporting source line range (within the scene). A scene with no
    present soul-class carries an empty list. Built by 13-cohort/cohort.py."""
    path = out_path(COHORT_DIR, canticle, canto)
    if not path.exists():
        print(f"Error: cohort not found: {path} (run 13-cohort/cohort.py first)", file=sys.stderr)
        sys.exit(1)
    out = {}
    for (s, e), body in scene_bodies(path).items():
        cohorts = []
        for line in body.splitlines():
            m = COHORT_LINE_RE.match(line)
            if m and m.group("src") != "none":
                bs = int(m.group("bs"))
                cohorts.append({
                    "cohort": m.group("cohort"),
                    "source": m.group("src"),
                    "basis_start": bs,
                    "basis_end": int(m.group("be")) if m.group("be") else bs,
                })
        out[(s, e)] = cohorts
    return out


# A topography `## <region-id>` heading and a `- runs:` run "<canto>:<ls>-<le>" item.
TOPO_RUN_RE = re.compile(r"^(?P<canto>\d+):(?P<ls>\d+)-(?P<le>\d+)$")


def load_topography(canticle):
    """{region_id: region} for a canticle from 10-topography/<canticle>.txt, or exit if absent.

    `region` is a dict: `en` (English gloss), `surfaces` (list of (form, count) source place-terms
    folded into the region), and `runs` (list of (canto, ls, le) — the contiguous source-line spans
    the region covers, in journey order). A scene (canto, s, e) belongs to the region whose run in
    that canto contains it (ls <= s, e <= le); the runs partition every scene of the canticle, so
    `region_of(canto, s, e)` is total. Built by 10-topography/topography.py; the region-id is a
    source-spelled representative term, the piecewise-constant fold of 09-location's surfaces."""
    path = TOPOGRAPHY_DIR / f"{canticle}.txt"
    if not path.exists():
        print(f"Error: topography not found: {path} (run 10-topography/topography.py first)",
              file=sys.stderr)
        sys.exit(1)
    out = {}
    region = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        h = REGISTRY_HEAD_RE.match(raw)
        if h:
            region = {"en": None, "surfaces": [], "runs": []}
            out[h.group(1)] = region
            continue
        if region is None:
            continue
        f = REGISTRY_FIELD_RE.match(raw)
        if not f:
            continue
        key, val = f.group(1), f.group(2).strip()
        if key == "en":
            region["en"] = val
        elif key == "surfaces":
            for item in (s.strip() for s in val.split(",") if s.strip()):
                m = re.match(r"^(.*\S)\s+\((\d+)\)$", item)
                if m:
                    region["surfaces"].append((m.group(1), int(m.group(2))))
        elif key == "runs":
            for item in (s.strip() for s in val.split(",") if s.strip()):
                m = TOPO_RUN_RE.match(item)
                if m:
                    region["runs"].append((int(m.group("canto")), int(m.group("ls")), int(m.group("le"))))
    return out


def load_kg(canticle):
    """The assembled KG for a canticle: {nodes, edges, speech_edges}, each a list read from the
    per-canticle 08-kg/<canticle>/{nodes,edges,speech_edges}.jsonl (exit if any is absent). One call
    for the whole graph; built by 08-kg/assembly.py (`make -C 08-kg`), see 08-kg/README.md.

    - nodes:       {id, type, members}  (members None unless a set node) — registry distilled to nodes.
    - edges:       {canto, scene, subj, predicate, obj, frame, lines, asserter}; subj/obj are
                   {tag, name, node} (node None if the label didn't resolve to a registry node).
    - speech_edges: {canto, quote_id, lines, speaker, signal, flags} — 06-speech spans (speaker -> span).
    Files: 08-kg/<canticle>/{nodes,edges,speech_edges}.jsonl"""
    return {
        "nodes": _load_kg_jsonl(canticle, "nodes"),
        "edges": _load_kg_jsonl(canticle, "edges"),
        "speech_edges": _load_kg_jsonl(canticle, "speech_edges"),
    }


def load_lock(canticle, canto):
    """The context lock for a canto: {canticle, canto, scenes}, parsed from the per-canto
    14-lock/<canticle>/NN.toml (exit if absent). `scenes` is the list of [[scene]] tables, each a
    dict {lines, title, location, region, cohort, cast, speech, refer, relations, simile, basis}:
    `cast` is [{who, status}]; `speech` is [{quote_id, lines, speaker, addressee, source}];
    `refer`/`relations`/`simile` are present only when non-empty. Identity and setting only — never
    the source's meaning. Built by 14-lock/lock.py (`make -C 14-lock`); see 14-lock/README.md."""
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        import tomli as tomllib
    path = LOCK_DIR / canticle / f"{canto:02d}.toml"
    if not path.exists():
        print(f"Error: lock not found: {path} (run 14-lock/lock.py first)", file=sys.stderr)
        sys.exit(1)
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    return {"canticle": doc["canticle"], "canto": doc["canto"], "scenes": doc.get("scene", [])}
