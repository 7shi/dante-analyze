"""Read-only query CLI over the committed analysis outputs
(scenes / reading / tags / registry / speech / relations / kg)."""
import argparse
import json
import sys

from ._paths import (
    SCENE_DIR, READING_DIR, TAGS_DIR, REGISTRY_DIR, SPEECH_DIR, RELATIONS_DIR, KG_DIR,
    TOPOGRAPHY_DIR, COHORT_DIR, LOCK_DIR,
)
from .checkpoint import out_path, load_digest, load_lock
from .corpus import load_scenes

_DIRS = {"reading": READING_DIR, "tags": TAGS_DIR, "speech": SPEECH_DIR, "relations": RELATIONS_DIR}


def _show(layer, canticle, canto):
    path = out_path(_DIRS[layer], canticle, canto)
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"), end="")


# Per-canticle registry-style outputs: one <canticle>.txt file (not per-canto).
_CANTICLE_DIRS = {"registry": REGISTRY_DIR, "topography": TOPOGRAPHY_DIR, "cohort": COHORT_DIR}


def _show_canticle(layer, canticle):
    path = _CANTICLE_DIRS[layer] / f"{canticle}.txt"
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"), end="")


def _show_kg(canticle, part):
    path = KG_DIR / canticle / f"{part}.jsonl"
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"), end="")


def _show_lock(canticle, canto):
    path = LOCK_DIR / canticle / f"{canto:02d}.toml"
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"), end="")


def _digest_paragraphs(scenes, locations, max_run=5):
    """Group consecutive scenes into reader paragraphs: a new paragraph begins where the 14-lock
    `location` changes, and a long same-location run is split so paragraphs stay ~3-5 per canto.
    `scenes` is [(s, e, name)] in order; `locations` is {(s, e): location}. Yields scene-key lists."""
    groups, cur, prev_loc = [], [], None
    for s, e, _name in scenes:
        loc = locations.get((s, e))
        if cur and (loc != prev_loc or len(cur) >= max_run):
            groups.append(cur)
            cur = []
        cur.append((s, e))
        prev_loc = loc
    if cur:
        groups.append(cur)
    return groups


def _show_digest(canticle, canto, lang):
    """Render the committed digest as continuous prose under `## Canto N`, scenes grouped into
    paragraphs on 14-lock `location` change. `lang` is `en`, `ja`, or `both`."""
    digest = load_digest(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    locations = {tuple(int(x) for x in sc["lines"].split("-")): sc.get("location")
                 for sc in load_lock(canticle, canto)["scenes"]}
    langs = ("en", "ja") if lang == "both" else (lang,)

    print(f"# Canto {canto:02d} — {canto_title}")
    for group in _digest_paragraphs(scenes, locations):
        print()
        for code in langs:
            sentences = [digest[key][code] for key in group
                         if key in digest and digest[key].get(code)]
            if sentences:
                print(" ".join(sentences))


def _show_scenes(canticle, canto):
    path = SCENE_DIR / canticle / f"{canto:02d}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"# Canto {canto:02d} — {payload['canto_title']}")
    for sc in sorted(payload["scenes"], key=lambda s: s["start_line"]):
        print(f"\n## Scene {sc['start_line']}-{sc['end_line']}: {sc['scene_name']}")
        if summary := sc.get("summary", ""):
            print(summary)


def build_parser():
    parser = argparse.ArgumentParser(prog="dante-analyze")
    roots = parser.add_subparsers(dest="layer", required=True)

    scenes_parser = roots.add_parser("scenes")
    scenes_sub = scenes_parser.add_subparsers(dest="action", required=True)
    scenes_show = scenes_sub.add_parser("show")
    scenes_show.add_argument("canticle")
    scenes_show.add_argument("canto", type=int)

    for layer in _CANTICLE_DIRS:
        layer_parser = roots.add_parser(layer)
        sub = layer_parser.add_subparsers(dest="action", required=True)
        show = sub.add_parser("show")
        show.add_argument("canticle")

    kg_parser = roots.add_parser("kg")
    kg_sub = kg_parser.add_subparsers(dest="action", required=True)
    kg_show = kg_sub.add_parser("show")
    kg_show.add_argument("canticle")
    kg_show.add_argument("part", nargs="?", default="edges", choices=("nodes", "edges", "speech_edges"))

    lock_parser = roots.add_parser("lock")
    lock_sub = lock_parser.add_subparsers(dest="action", required=True)
    lock_show = lock_sub.add_parser("show")
    lock_show.add_argument("canticle")
    lock_show.add_argument("canto", type=int)

    digest_parser = roots.add_parser("digest")
    digest_sub = digest_parser.add_subparsers(dest="action", required=True)
    digest_show = digest_sub.add_parser("show")
    digest_show.add_argument("canticle")
    digest_show.add_argument("canto", type=int)
    digest_show.add_argument("--lang", choices=("en", "ja", "both"), default="both",
                             help="which language(s) to render (default: both)")

    for layer in _DIRS:
        layer_parser = roots.add_parser(layer)
        sub = layer_parser.add_subparsers(dest="action", required=True)
        show = sub.add_parser("show")
        show.add_argument("canticle")
        show.add_argument("canto", type=int)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.action == "show":
            if args.layer == "scenes":
                _show_scenes(args.canticle, args.canto)
            elif args.layer in _CANTICLE_DIRS:
                _show_canticle(args.layer, args.canticle)
            elif args.layer == "kg":
                _show_kg(args.canticle, args.part)
            elif args.layer == "lock":
                _show_lock(args.canticle, args.canto)
            elif args.layer == "digest":
                _show_digest(args.canticle, args.canto, args.lang)
            else:
                _show(args.layer, args.canticle, args.canto)
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown action: {args.action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
