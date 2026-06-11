"""
Scene reading for Dante's Divine Comedy (analysis step, pre-processing).

This is the FREE-INTERPRETATION pass, split out of bullets.py's old Turn 1. For each
scene it produces a plain-English reading: who does what, who speaks to whom, and —
for each numbered tag in the markup — which person it refers to. The reading is
prose, non-deterministic, and NOT machine-checkable (there is no round-trip and no
coverage anchor on free prose), so it carries NO logic check; it is committed and
HAND-PROOFREAD instead, and bullets.py then re-grounds it to the numbered tags under
a coverage check (ARCHITECTURE §11). Proofreading a reading is the lever that
improves the downstream bullets.

It sits BETWEEN markup.py (NN-4) and bullets.py:
    markup.py  -> every person-reference marked, numbered by scenelib
    reading.py -> a free prose reading per scene (this script)        [committed]
    bullets.py -> tag-citing bullets + [n] = Name resolution          [coverage-checked]

One generation pass (`-m`, the larger Gemma — the stronger reader) per scene, with
chain-of-thought ON by default (`--no-think` disables it, as in bullets.py / tags.py):
this is the uncheckable, precision-critical layer, so the model is allowed to think
(slower) and there is no structured output for CoT to corrupt — the thinking stays
internal, the saved text is clean prose. The reading of earlier scenes this canto
plus a short recap carried from the previous canto are given as context, so prior
scenes are nameable; a `# recap` block is written at the canto's end for the next.

Input:  02-markup/<canticle>/NN-4.txt           (markup.py final output; run it first)
        scene ranges + names                 (from the dante_corpus API)
Output: 03-reading/<canticle>/NN.txt            (committed, hand-editable). Per scene a
        `## Scene s-e: name` prose block; a `# recap` block per canto carried to the
        next. The file is the checkpoint: a scene already present is skipped, so an
        interrupted run resumes. Delete the file to regenerate a canto.
"""
import argparse
import sys

from dante_analyze import (
    READING_DIR, LLM_RETRIES, available_cantos, load_scenes, read_markup, number_scene,
    parse_bullets, call_llm, step_sep, build_reason_prompt,
    out_path, complete_scene_ends, read_recap, iter_scene_blocks,
    render_scene_block, append_canto,
)

OUT_DIR = READING_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"  # the larger, stronger reader (precision over speed)


# ---------- recap (carry-forward to the next canto) ----------

def make_recap(canto, canto_title, readings, model, include_thoughts):
    """Carry a short recap of the canto's end-state to the next canto. CoT follows the
    run's setting (`include_thoughts`, ON by default like the scene reading): a hosted
    Gemma (Google backend) does NOT actually disable thinking when asked to — it just
    leaks the reasoning into the body — so forcing CoT off poisons the recap with
    prompt-echo and meta-commentary bullets. With CoT on, the thinking stays in its own
    channel and `resp.text` is the clean bullet list. `readings` is the canto's
    accumulated prose reading."""
    prompt = f"""Here is the scene-by-scene reading of Canto {canto} ("{canto_title}"):

{readings}

In 1-3 short bullet lines, state where things stand at the END of this canto: which
named persons are on stage / travelling together, and the immediate situation. This
is a hand-off note for the next canto. Output only `- ` bullet lines, nothing else."""
    resp = call_llm([{"role": "user", "content": prompt}], model, include_thoughts=include_thoughts)
    return "\n".join(f"- {b}" for b in parse_bullets(resp.text))


# ---------- per-scene / per-canto driver ----------

def read_scene(canto, canto_title, s, e, scene_name, tagged, prior, recap, model, include_thoughts):
    """Produce one scene's free prose reading with `model`. CoT follows the run's setting
    (`include_thoughts`, ON by default): this is the uncheckable, precision-critical
    interpretation layer, so the model gets to think (slower) and there is no
    structured output for CoT to corrupt — the thinking stays internal, the saved
    text is clean prose. NO check: free prose is not tag-anchored (it is
    hand-proofread); digest.py applies the coverage check."""
    step_sep("reading")
    prompt = build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, prior, recap)
    resp = call_llm([{"role": "user", "content": prompt}], model, include_thoughts=include_thoughts)
    prose = resp.text.strip()
    if not prose:
        # call_llm already regenerated on an empty reply; if the body is STILL empty the
        # model spent the whole budget thinking (CoT runaway cut off before any prose).
        # Do NOT commit a blank scene (it would block digest/tags and silently count as
        # done on resume) and do NOT pass off the CoT thoughts as the reading — they are
        # not the prose. Fail hard so the run stops; rerun to retry just this scene.
        print(f"Error: reading generation produced no prose for scene {s}-{e} "
              f'"{scene_name}" after {LLM_RETRIES} attempts; aborting (rerun to retry).',
              file=sys.stderr)
        sys.exit(1)
    return prose


def prior_readings(path):
    """The prose readings of scenes already in this canto's file, as continuity
    context for the next scene (full `## Scene` blocks, in order)."""
    return "\n\n".join(block for _, _, block in iter_scene_blocks(path))


def read_canto(canticle, canto, model, include_thoughts):
    """Generate one canto's reading, scene by scene, carrying a recap from the
    previous canto. The output file (NN.txt) is the checkpoint: each finished scene
    is written as it completes and skipped on resume."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    path = out_path(OUT_DIR, canticle, canto)
    recap = read_recap(out_path(OUT_DIR, canticle, canto - 1))

    # Count only scenes with a non-empty body as done; a blank block (an earlier failed
    # generation) is dropped from `blocks` and regenerated below, so a rerun self-heals.
    done = complete_scene_ends(path)
    blocks = [f"{block}\n" for _s, e, block in iter_scene_blocks(path) if e in done]

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        tagged, _k, _meta = number_scene(lines, s, e)
        prose = read_scene(canto, canto_title, s, e, scene_name, tagged,
                           prior_readings(path), recap, model, include_thoughts)
        blocks.append(render_scene_block(s, e, scene_name, prose))
        append_canto(path, canto, canto_title, blocks)
        print(f"saved scene {s}-{e} to {path}")

    readings = "\n\n".join(block for _, _, block in iter_scene_blocks(path))
    recap = make_recap(canto, canto_title, readings, model, include_thoughts)
    append_canto(path, canto, canto_title, blocks, recap=recap)
    print(f"\nCanto {canto} written to {path}")


def cmd_run(canticle, model, only_canto, include_thoughts):
    cantos = available_cantos(canticle)
    if not cantos:
        print(f"Error: no NN-4 markup for {canticle} (run markup.py first)", file=sys.stderr)
        sys.exit(1)
    if only_canto is not None:
        if only_canto not in cantos:
            print(f"Error: Canto {only_canto} not found for {canticle} "
                  f"(no 02-markup/{canticle}/{only_canto:02d}-4.txt)", file=sys.stderr)
            sys.exit(1)
        targets = [only_canto]
    else:
        targets = cantos

    for canto in targets:
        path = out_path(OUT_DIR, canticle, canto)
        if path.exists():
            _, scenes = load_scenes(canticle, canto)
            # Complete only if every scene is written AND the recap is present; deleting
            # the recap alone forces read_canto to regenerate just the recap (all scenes
            # load as done and are skipped).
            if complete_scene_ends(path) >= {e for _, e, _ in scenes} and read_recap(path):
                print(f"Canto {canto}: already complete at {path}, skipping.")
                continue
        read_canto(canticle, canto, model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Free prose reading per scene for Dante's Divina Commedia: who "
                    "does what / who speaks, with each numbered tag resolved (see PLAN.md).")
    parser.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"LLM for generation (default: {DEFAULT_MODEL})")
    parser.add_argument("-c", "--canto", type=int,
                        help="Process only this canto. The output file (NN.txt) is the "
                             "checkpoint; delete it to regenerate a completed canto.")
    parser.add_argument("--no-think", action="store_true",
                        help="Disable chain-of-thought (CoT is ON by default for this pass).")
    args = parser.parse_args()

    for canticle in args.canticles:
        cmd_run(canticle, args.model, args.canto, not args.no_think)


if __name__ == "__main__":
    main()
