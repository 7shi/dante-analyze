"""Corpus input readers: load markup lines, scene ranges/names, and the list of
available cantos from the on-disk analysis artefacts."""
import json
import sys

from ._paths import SCENE_DIR, MARKUP_DIR


def read_markup(canticle, canto):
    """The marked lines (one per source line) for a canto, or exit if absent."""
    path = MARKUP_DIR / canticle / f"{canto:02d}.txt"
    if not path.exists():
        print(f"Error: markup not found: {path} (run 02-markup/markup.py first)", file=sys.stderr)
        sys.exit(1)
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def available_cantos(canticle):
    """Cantos that have a finished markup file, in order."""
    d = MARKUP_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem[:2]) for p in d.glob("[0-9][0-9].txt"))


def load_scenes(canticle, canto):
    """(canto_title, [(start, end, scene_name), …]) from scene JSON."""
    path = SCENE_DIR / canticle / f"{canto:02d}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenes = sorted(
        (s["start_line"], s["end_line"], s["scene_name"])
        for s in payload["scenes"]
    )
    return payload["canto_title"], scenes
