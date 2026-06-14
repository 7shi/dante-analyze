from ._paths import (
    SCENE_DIR, MARKUP_DIR, READING_DIR, TAGS_DIR, REGISTRY_DIR, SPEECH_DIR, RELATIONS_DIR, KG_DIR,
)
from .llm import MAX_LENGTH, LLM_RETRIES, call_llm, step_sep
from .corpus import read_markup, available_cantos, load_scenes
from .marks import number_scene, tag_positions, strip_to_source, parse_bullets, unbrace, fix_elision, ELIDE_RE
from .labels import (
    norm_label, fold_key, split_set, is_capitalized_name,
    FIRST_PERSON_STRONG, FIRST_PERSON_WEAK, FIRST_PERSON_PLURAL,
)
from .quotespans import walk_spans, contains, own_region
from .checkpoint import (
    TAGS_LINE_RE,
    out_path, done_scene_ends, read_recap, iter_scene_blocks, scene_bodies,
    complete_scene_ends, restore_blocks, render_scene_block, append_canto,
    load_readings, load_tags, load_registry, load_speech, load_relations,
    raw_to_canonical, load_kg,
)
from .prompts import build_reason_prompt

__all__ = [
    # output dirs (project root)
    "SCENE_DIR", "MARKUP_DIR", "READING_DIR", "TAGS_DIR", "REGISTRY_DIR", "SPEECH_DIR",
    "RELATIONS_DIR", "KG_DIR",
    # LLM boundary
    "MAX_LENGTH", "LLM_RETRIES", "call_llm", "step_sep",
    # inputs / corpus
    "read_markup", "available_cantos", "load_scenes",
    # output readers
    "load_readings", "load_tags", "load_registry", "load_speech", "load_relations",
    "raw_to_canonical", "load_kg",
    "scene_bodies", "iter_scene_blocks",
    "done_scene_ends", "complete_scene_ends", "read_recap", "restore_blocks",
    # tag numbering / parsing
    "number_scene", "tag_positions", "strip_to_source", "parse_bullets", "unbrace",
    # label normalization / classification (registry)
    "norm_label", "fold_key", "split_set", "is_capitalized_name",
    "FIRST_PERSON_STRONG", "FIRST_PERSON_WEAK", "FIRST_PERSON_PLURAL",
    # quote-span geometry (speech)
    "walk_spans", "contains", "own_region",
    # elision repair
    "fix_elision", "ELIDE_RE", "TAGS_LINE_RE",
    # prompts / checkpoint writing
    "build_reason_prompt", "out_path", "render_scene_block", "append_canto",
]
