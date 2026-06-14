"""Read-only query CLI over the committed analysis outputs
(scenes / reading / tags / registry / speech / relations)."""
import argparse
import json
import sys

from ._paths import SCENE_DIR, READING_DIR, TAGS_DIR, REGISTRY_DIR, SPEECH_DIR, RELATIONS_DIR
from .checkpoint import out_path

_DIRS = {"reading": READING_DIR, "tags": TAGS_DIR, "speech": SPEECH_DIR, "relations": RELATIONS_DIR}


def _show(layer, canticle, canto):
    path = out_path(_DIRS[layer], canticle, canto)
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"), end="")


def _show_registry(canticle):
    path = REGISTRY_DIR / f"{canticle}.txt"
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"), end="")


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

    registry_parser = roots.add_parser("registry")
    registry_sub = registry_parser.add_subparsers(dest="action", required=True)
    registry_show = registry_sub.add_parser("show")
    registry_show.add_argument("canticle")

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
            elif args.layer == "registry":
                _show_registry(args.canticle)
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
