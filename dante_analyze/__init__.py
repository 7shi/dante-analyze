from ._paths import SCENE_DIR, MARKUP_DIR, READING_DIR, TAGS_DIR
from .llm import MAX_LENGTH, LLM_RETRIES, call_llm, step_sep
from .corpus import read_markup, available_cantos, load_scenes
from .marks import number_scene, parse_bullets, unbrace, fix_elision, ELIDE_RE
from .checkpoint import (
    TAGS_LINE_RE,
    out_path, done_scene_ends, read_recap, iter_scene_blocks, scene_bodies,
    complete_scene_ends, restore_blocks, render_scene_block, append_canto,
    load_readings, load_tags,
)
from .prompts import build_reason_prompt

__all__ = [
    # output dirs (project root)
    "SCENE_DIR", "MARKUP_DIR", "READING_DIR", "TAGS_DIR",
    # LLM boundary
    "MAX_LENGTH", "LLM_RETRIES", "call_llm", "step_sep",
    # inputs / corpus
    "read_markup", "available_cantos", "load_scenes",
    # output readers
    "load_readings", "load_tags", "scene_bodies", "iter_scene_blocks",
    "done_scene_ends", "complete_scene_ends", "read_recap", "restore_blocks",
    # tag numbering / parsing
    "number_scene", "parse_bullets", "unbrace",
    # elision repair
    "fix_elision", "ELIDE_RE", "TAGS_LINE_RE",
    # prompts / checkpoint writing
    "build_reason_prompt", "out_path", "render_scene_block", "append_canto",
]
