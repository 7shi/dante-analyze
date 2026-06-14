#!/usr/bin/env python
"""
KG assembly — Step 4 of the knowledge graph.

Pure code, no LLM. Joins the committed upstream outputs into the assembled graph by reading them
through the dante_analyze load_* public API only:
  - 07-relations edges (cited [n] tags)  -> resolved subj/obj nodes + asserter
  - 06-speech spans (speaker per quote)  -> speech edges, and the asserter source
  - 04-tags labels                       -> the per-scene [n] -> name table
  - 05-registry nodes                    -> name -> canonical node (via raw_to_canonical/fold_key)

Per canticle, per canto, every relation edge's line range falls inside exactly one 04-tags scene
(scenes partition the canto), so the scene — and therefore each cited [n]'s name — is recoverable;
the name canonicalizes to a registry node through fold_key. For reported/prophecy/simile edges the
ASSERTER is the speaker of the innermost 06-speech quote span containing the edge's line range;
literal edges are narrated and have no asserter (07-relations/README.md "Step-4 assembly contract").

Pipeline: load committed inputs (code) -> resolve edge ends to nodes (code) -> recover asserter
(code) -> render per-canto JSON + per-canticle node table (code) -> structural check (code).

Input:  07-relations/<canticle>/NN.txt  (committed; edges)
        06-speech/<canticle>/NN.txt     (committed; speaker per quote span)
        04-tags/<canticle>/NN.txt       (committed; per-scene [n] -> name)
        05-registry/<canticle>.txt      (committed; canonical node table)
Output (per canticle, JSONL — one record per line, all cantos aggregated):
        08-kg/<canticle>/nodes.jsonl    one node per line  {id, type, members}
        08-kg/<canticle>/edges.jsonl    one edge per line  {canto, scene, subj, predicate, obj, frame, lines, asserter}
        08-kg/<canticle>/speech_edges.jsonl   one speech edge per line  {canto, quote_id, lines, speaker, signal, flags}
"""
import argparse
import json
import sys

from dante_analyze import (
    KG_DIR, RELATIONS_DIR,
    load_tags, load_relations, load_speech, load_registry, load_scenes,
    raw_to_canonical, norm_label, fold_key,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
UNATTRIBUTED = "(unattributed)"
ASSERTING_FRAMES = {"reported", "prophecy", "simile"}


def committed_cantos(canticle):
    """Cantos with a committed 07-relations file, in order; the file is the checkpoint."""
    d = RELATIONS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


def build_nodes(registry):
    """[{id, type, members}] — the registry distilled to graph nodes. `id` is the canonical
    heading; `members` is the member list for a set node, else None (surfaces/labels are dropped:
    the graph references nodes by id)."""
    nodes = []
    for canonical, node in registry.items():
        members = node["members"] or None
        nodes.append({"id": canonical, "type": node["type"], "members": members})
    return nodes


def scene_of(tags, start, end):
    """The unique scene range (s, e) in `tags` containing the line range [start, end], or None
    if zero or more than one contains it (a geometry failure the check reports)."""
    hits = [(s, e) for (s, e) in tags if s <= start and end <= e]
    return hits[0] if len(hits) == 1 else None


def resolve_end(tags, scene, raw2canon, tag_no, problems, where):
    """{tag, name, node} for one edge end. `node` is the registry canonical (or None if the label
    is (unknown) / an un-registered surface — tallied, not fatal). A missing tag_no in the scene is
    a geometry failure (appended to `problems`)."""
    names = tags[scene]
    if tag_no not in names:
        problems.append(f"{where}: tag [{tag_no}] not in scene {scene[0]}-{scene[1]} {sorted(names)}")
        return {"tag": tag_no, "name": None, "node": None}
    name = names[tag_no]
    node = raw2canon.get(fold_key(norm_label(name)))
    return {"tag": tag_no, "name": name, "node": node}


def asserter_of(edge, speech):
    """The speaker of the innermost 06-speech span containing the edge's line range, for an
    asserting frame; None for literal, for an (unattributed) container, or when no span contains
    the range."""
    if edge["frame"] not in ASSERTING_FRAMES:
        return None
    containing = [sp for sp in speech if sp["start"] <= edge["start"] and edge["end"] <= sp["end"]]
    if not containing:
        return None
    inner = min(containing, key=lambda sp: sp["end"] - sp["start"])
    return None if inner["speaker"] == UNATTRIBUTED else inner["speaker"]


def render_canto(canticle, canto, raw2canon):
    """(payload, problems) for a canto: the JSON dict to write plus structural problems (geometry
    failures abort; unresolved nodes / missing asserters are tallied via the returned payload)."""
    tags = load_tags(canticle, canto)
    rels = load_relations(canticle, canto)
    speech = load_speech(canticle, canto)

    problems = []
    edges = []
    for edge in rels:
        scene = scene_of(tags, edge["start"], edge["end"])
        if scene is None:
            problems.append(f"edge lines {edge['start']}-{edge['end']} in 0 or >1 scenes")
            continue
        where = f"edge {edge['start']}-{edge['end']}"
        subj = resolve_end(tags, scene, raw2canon, edge["subj"], problems, where + " subj")
        obj = resolve_end(tags, scene, raw2canon, edge["obj"], problems, where + " obj")
        edges.append({
            "canto": canto,
            "scene": [scene[0], scene[1]],
            "subj": subj,
            "predicate": edge["predicate"],
            "obj": obj,
            "frame": edge["frame"],
            "lines": [edge["start"], edge["end"]],
            "asserter": asserter_of(edge, speech),
        })

    speech_edges = [
        {"canto": canto, "quote_id": sp["quote_id"], "lines": [sp["start"], sp["end"]],
         "speaker": sp["speaker"], "signal": sp["signal"], "flags": sp["flags"]}
        for sp in speech
    ]
    return edges, speech_edges, problems


def write_jsonl(path, records):
    """One JSON object per line (JSONL)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                    encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="KG assembly (Step 4): join relations + speech + tags + registry into the "
                    "graph (see 08-kg/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to build (default: all three)")
    args = ap.parse_args()

    failed = False
    for canticle in args.canticles:
        cantos = committed_cantos(canticle)
        if not cantos:
            print(f"(skip {canticle}: no committed 07-relations)", file=sys.stderr)
            continue
        registry = load_registry(canticle)
        raw2canon = raw_to_canonical(canticle)

        all_edges, all_speech_edges, canticle_problems = [], [], False
        for canto in cantos:
            edges, speech_edges, problems = render_canto(canticle, canto, raw2canon)
            if problems:
                canticle_problems = failed = True
                print(f"\nkg {canticle} {canto:02d}: {len(problems)} STRUCTURAL problem(s):",
                      file=sys.stderr)
                for p in problems:
                    print(f"- {p}", file=sys.stderr)
                continue
            all_edges.extend(edges)
            all_speech_edges.extend(speech_edges)

        if canticle_problems:
            print(f"kg {canticle}: SKIPPED write ({len(cantos)} cantos had problems)", file=sys.stderr)
            continue

        write_jsonl(KG_DIR / canticle / "nodes.jsonl", build_nodes(registry))
        write_jsonl(KG_DIR / canticle / "edges.jsonl", all_edges)
        write_jsonl(KG_DIR / canticle / "speech_edges.jsonl", all_speech_edges)
        unresolved = sum(1 for e in all_edges for end in (e["subj"], e["obj"])
                         if end["node"] is None)
        print(f"kg {canticle}: OK — {len(cantos)} cantos, {len(build_nodes(registry))} nodes, "
              f"{len(all_edges)} edges, {len(all_speech_edges)} speech_edges "
              f"({unresolved} unresolved edge ends)", file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
