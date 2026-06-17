#!/usr/bin/env python
"""
Context lock — the last pass of the translation context lock (PLAN.md direction 1).

Pure code, no LLM. Joins the five committed context-lock layers plus the assembled KG into a
per-scene identity-and-setting record — what a translation or digest must not get wrong: where the
scene is set, which class of souls dwells there, who is present versus merely mentioned, who speaks
and is addressed, which referring expressions resolve to which figure, and the literal / simile
relations among them. Identity and setting only — never the source's meaning or a paraphrase. It is
the setting layer 08-kg (action-only) does not carry, plus the KG's resolved figures, per scene.

Read through the dante_analyze load_* public API only (no cross-pass imports):
  - 01-scenes      load_scenes      -> the canonical scene segmentation (s, e) + titles
  - 09-location    load_locations   -> per-scene primary current setting ("it")
  - 10-topography  load_topography  -> canonical region a scene belongs to (via its runs)
  - 11-presence    load_presence    -> cast: who is present vs merely mentioned
  - 12-addressee   load_addressee   -> per speech span: speaker + addressee
  - 13-cohort      load_cohort      -> which soul-class(es) dwell in the scene
  - 08-kg          load_kg          -> resolved edges -> refer / relations / simile per scene

Per canticle, per canto: every layer is keyed to the same (s, e) scene segmentation, so the join is
a deterministic gather. The scene's region is the unique 10-topography region whose run in this canto
contains the scene; KG edges carry their own scene, so they filter to the scene by equality.

Structural check (fail-loud; a problem skips the whole canticle's write, as 08-kg does):
  - every scene of the canto gets exactly one lock entry (the per-scene layers cover the scene set);
  - every scene resolves to exactly one region (the topography runs are total);
  - every basis / cited line range falls inside its scene.

Input:  01-scenes/<canticle>/NN.json    (committed; scene segmentation)
        09-location..13-cohort           (committed; the five lock layers)
        08-kg/<canticle>/*.jsonl         (committed; assembled graph)
Output: 14-lock/<canticle>/NN.toml       (per canto; one [[scene]] table per scene)
"""
import argparse
import sys

from dante_analyze import (
    LOCK_DIR, SCENE_DIR, load_scenes,
    load_locations, load_topography, load_presence, load_addressee, load_cohort, load_kg,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
CARRIED = "-"  # 09-location marker: setting carried forward from the previous scene


def committed_cantos(canticle):
    """Cantos with a committed 01-scenes file, in order; the segmentation drives every layer."""
    d = SCENE_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].json"))


def region_of(topography, canto, s, e):
    """The unique region id whose run in `canto` contains the scene [s, e], or None if zero or more
    than one does (a geometry failure the check reports)."""
    hits = [rid for rid, region in topography.items()
            if any(rc == canto and ls <= s and e <= le for (rc, ls, le) in region["runs"])]
    return hits[0] if len(hits) == 1 else None


def in_scene(s, e, a, b):
    """Whether the line range [a, b] falls inside the scene [s, e]."""
    return s <= a and b <= e


def primary_location(locs, carried):
    """The scene's primary current setting: the first concrete `it` of 09-location, or the value
    carried from the previous scene when the scene only marks a carry (`-`)."""
    if locs and locs[0]["it"] != CARRIED:
        return locs[0]["it"]
    return carried


def edge_party(end):
    """The canonical node of one edge end, falling back to the surface label if it didn't resolve."""
    return end["node"] or end["name"]


def scene_edges(edges_by_scene, canto, s, e):
    """The KG edges whose scene is exactly this scene, in source order."""
    return edges_by_scene.get((canto, s, e), [])


def build_scene(canticle, canto, s, e, title, locs, topography, presence, addressee, cohort,
                edges, carried, problems):
    """The lock record for one scene (a dict mirroring the [[scene]] table), appending any
    structural problems found while joining."""
    where = f"canto {canto} scene {s}-{e}"

    region = region_of(topography, canto, s, e)
    if region is None:
        problems.append(f"{where}: in 0 or >1 topography regions")

    for loc in locs:
        if loc["it"] != CARRIED and not in_scene(s, e, loc["basis_start"], loc["basis_end"]):
            problems.append(f"{where}: location basis {loc['basis_start']}-{loc['basis_end']} outside scene")
    for fig in presence:
        if not in_scene(s, e, fig["basis_start"], fig["basis_end"]):
            problems.append(f"{where}: presence basis for {fig['who']} outside scene")

    cast = [{"who": fig["who"], "status": fig["status"]} for fig in presence]

    speech = []
    for sp in addressee:
        # 12-addressee keys a span by the scene holding its START line; a cross-scene quote may end
        # past the scene, so only the start is required in-scene.
        if not (s <= sp["start"] <= e):
            problems.append(f"{where}: speech span {sp['quote_id']} starts {sp['start']} outside scene")
        speech.append({
            "quote_id": sp["quote_id"],
            "lines": f"{sp['start']}-{sp['end']}",
            "speaker": sp["speaker"],
            "addressee": sp["addressee"],
            "source": sp["source"],
        })

    refer, relations, simile = [], [], []
    for edge in edges:
        for end in (edge["subj"], edge["obj"]):
            # A surface that resolved to a differently-spelled canonical: an identity the
            # translation must not get from the surface form alone.
            if end["node"] and end["name"] and end["node"] != end["name"]:
                entry = {"phrase": end["name"], "line": edge["lines"][0], "resolves": end["node"]}
                if entry not in refer:
                    refer.append(entry)
        lines = f"{edge['lines'][0]}-{edge['lines'][1]}"
        if edge["frame"] == "literal":
            entry = {"subj": edge_party(edge["subj"]), "predicate": edge["predicate"],
                     "obj": edge_party(edge["obj"]), "lines": lines}
            if entry not in relations:
                relations.append(entry)
        elif edge["frame"] == "simile":
            entry = {"lines": lines, "vehicle": edge_party(edge["obj"])}
            if entry not in simile:
                simile.append(entry)

    return {
        "lines": f"{s}-{e}",
        "title": title,
        "location": primary_location(locs, carried),
        "region": region,
        "cohort": [c["cohort"] for c in cohort],
        "cast": cast,
        "speech": speech,
        "refer": refer,
        "relations": relations,
        "simile": simile,
        "basis": f"{s}-{e}",
    }


def render_canto(canticle, canto, topography, edges_by_scene):
    """(scenes, problems) for a canto: the list of lock records plus structural problems."""
    _, scenes = load_scenes(canticle, canto)
    locations = load_locations(canticle, canto)
    presence = load_presence(canticle, canto)
    addressee = load_addressee(canticle, canto)
    cohort = load_cohort(canticle, canto)

    problems = []
    scene_keys = {(s, e) for (s, e, _) in scenes}
    for layer, data in (("location", locations), ("presence", presence), ("cohort", cohort)):
        missing = scene_keys - set(data)
        if missing:
            problems.append(f"canto {canto}: {layer} missing scenes {sorted(missing)}")

    records, carried = [], None
    for (s, e, title) in scenes:
        rec = build_scene(
            canticle, canto, s, e, title,
            locations.get((s, e), []), topography, presence.get((s, e), []),
            addressee.get((s, e), []), cohort.get((s, e), []),
            scene_edges(edges_by_scene, canto, s, e), carried, problems,
        )
        carried = rec["location"]
        records.append(rec)
    return records, problems


# ---- TOML rendering (Python has no stdlib writer; mirror ref/inferno-01.toml's layout) ----

def _toml_str(s):
    """A TOML basic string (double-quoted, backslash/quote/control escaped)."""
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return f'"{out}"'


def _toml_value(v):
    """Scalar / list scalar value as TOML (str, int, or array of strings)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_str(x) for x in v) + "]"
    return _toml_str(v)


def _inline_table(d):
    """A TOML inline table: { k = v, … } in insertion order."""
    return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in d.items()) + " }"


def _emit_array_of_tables(key, rows):
    """`key = [` … one `  { … },` per row … `]` — the readable, hand-editable layout."""
    lines = [f"{key} = ["]
    lines += [f"  {_inline_table(r)}," for r in rows]
    lines.append("]")
    return lines


def render_toml(canticle, canto, scenes):
    """The full per-canto TOML text for the lock."""
    out = [f"canticle = {_toml_str(canticle)}", f"canto = {canto}", ""]
    for sc in scenes:
        out.append("[[scene]]")
        out.append(f"lines = {_toml_str(sc['lines'])}")
        out.append(f"title = {_toml_str(sc['title'])}")
        out.append(f"location = {_toml_str(sc['location'])}" if sc["location"] is not None
                   else "location = \"\"")
        out.append(f"region = {_toml_str(sc['region'])}" if sc["region"] is not None
                   else 'region = ""')
        if sc["cohort"]:
            out.append(f"cohort = {_toml_value(sc['cohort'])}")
        out += _emit_array_of_tables("cast", sc["cast"]) if sc["cast"] else ["cast = []"]
        for key in ("speech", "refer", "relations", "simile"):
            if sc[key]:
                out += _emit_array_of_tables(key, sc[key])
        out.append(f"basis = {_toml_str(sc['basis'])}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def write_canto(canticle, canto, scenes):
    path = LOCK_DIR / canticle / f"{canto:02d}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_toml(canticle, canto, scenes), encoding="utf-8")


def index_edges(kg):
    """{(canto, s, e): [edge, …]} — KG edges grouped by the scene they carry."""
    by_scene = {}
    for edge in kg["edges"]:
        key = (edge["canto"], edge["scene"][0], edge["scene"][1])
        by_scene.setdefault(key, []).append(edge)
    return by_scene


def main():
    ap = argparse.ArgumentParser(
        description="Context lock (PLAN.md direction 1, last pass): join the five lock layers + KG "
                    "into per-scene identity/setting records (see 14-lock/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to build (default: all three)")
    args = ap.parse_args()

    failed = False
    for canticle in args.canticles:
        cantos = committed_cantos(canticle)
        if not cantos:
            print(f"(skip {canticle}: no committed 01-scenes)", file=sys.stderr)
            continue
        topography = load_topography(canticle)
        edges_by_scene = index_edges(load_kg(canticle))

        per_canto, canticle_problems = {}, False
        for canto in cantos:
            records, problems = render_canto(canticle, canto, topography, edges_by_scene)
            if problems:
                canticle_problems = failed = True
                print(f"\nlock {canticle} {canto:02d}: {len(problems)} STRUCTURAL problem(s):",
                      file=sys.stderr)
                for p in problems:
                    print(f"- {p}", file=sys.stderr)
                continue
            per_canto[canto] = records

        if canticle_problems:
            print(f"lock {canticle}: SKIPPED write (some cantos had problems)", file=sys.stderr)
            continue

        scenes = 0
        for canto, records in per_canto.items():
            write_canto(canticle, canto, records)
            scenes += len(records)
        print(f"lock {canticle}: OK — {len(cantos)} cantos, {scenes} scene locks", file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
