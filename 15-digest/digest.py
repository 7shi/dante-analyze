#!/usr/bin/env python
"""
Digest edition for Dante's Divina Commedia — the FIRST CONSUMER of the translation context lock
(PLAN.md direction 1), and its proof.

For each scene it produces a 1-2 sentence bilingual (English + Japanese) retelling at story-reading
density: more than a plot summary, lighter than a translation. The point is not only the digest but
a demonstration that 14-lock is what keeps a retelling from getting identities and settings wrong:
the lock is the PRIMARY INPUT — the closed who/where vocabulary — and the digest may not introduce a
name, place, or soul-class the lock does not list for the scene. 03-reading supplies WHAT happens.

Per scene, a two-turn conversation (the "split deliberation from final output" pattern, as tags.py
replays the reading):
    Turn 1 user      = build_reason_prompt(..., prior="", recap="")   # reconstruct the reading's question
    Turn 1 assistant = the committed 03-reading prose for the scene   # the resolved events, replayed
    Turn 2 user      = build_digest_prompt(..., lock_scene, prior)    # constrain to the lock vocabulary
    -> English 1-2 sentences
Then a second call translates that English into Japanese, keeping every name in SOURCE spelling
(build_digest_translate_prompt), so the lock-conformance vocabulary is preserved across languages.

Chain-of-thought is ON by default (`--no-think` disables it, as in reading.py): the digest is
uncheckable free prose, so the model is allowed to think and there is no structured output for CoT
to corrupt — the saved text is clean prose. Lock conformance is measured separately by conformance.py.

Input:  03-reading/<canticle>/NN.txt   (committed; the resolved events — run reading.py first)
        14-lock/<canticle>/NN.toml     (committed; the closed who/where vocabulary — run lock.py first)
        02-markup + scene ranges       (to reconstruct the reading's Turn-1, via the dante_corpus API)
Output: 15-digest/<canticle>/NN.txt    (committed, hand-editable). Per scene a `## Scene s-e: name`
        block with an `en:` and a `ja:` line. The file is the checkpoint: a scene with a non-empty
        body is skipped on resume. Delete the file to regenerate a canto.
"""
import argparse
import re
import sys

from dante_analyze import (
    DIGEST_DIR, LLM_RETRIES, available_cantos, load_scenes, read_markup, number_scene,
    load_readings, load_lock, load_digest, split_set, call_llm, step_sep,
    build_reason_prompt, build_digest_prompt, build_digest_translate_prompt,
    out_path, complete_scene_ends, iter_scene_blocks, render_scene_block, append_canto,
)

OUT_DIR = DIGEST_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"  # the larger, stronger reader (precision over speed)


def lock_by_scene(canticle, canto):
    """{(start, end): lock_scene} for a canto — the 14-lock entries keyed by their scene range."""
    out = {}
    for sc in load_lock(canticle, canto)["scenes"]:
        s, e = (int(x) for x in sc["lines"].split("-"))
        out[(s, e)] = sc
    return out


def lock_names(lock_scene):
    """The source-spelling names the scene's lock entry licenses — cast figures plus speech parties.
    Passed to the translator so the Japanese keeps exactly these surfaces."""
    names = [fig["who"] for fig in lock_scene.get("cast", [])]
    for sp in lock_scene.get("speech", []):
        for party in (sp.get("speaker"), sp.get("addressee")):
            if party and party not in ("(none)", "(unattributed)") and party not in names:
                names.append(party)
    return names


def scene_terms(lock_scene, all_whos):
    """The full source-spelling surfaces a scene's lock licenses — every cast figure (and the members
    of a set label), speech party, setting, soul-class, and KG-resolved name. These are the Italian
    terms the English digest embeds; mark_italian wraps them so they stand out as they do, by being
    Latin script, in the Japanese line."""
    terms = set()

    def add(label):
        if label and label not in ("(none)", "(unattributed)"):
            terms.add(label)
            members = split_set(label, all_whos)
            if members:
                terms.update(members)

    for fig in lock_scene.get("cast", []):
        add(fig["who"])
    for sp in lock_scene.get("speech", []):
        add(sp.get("speaker"))
        add(sp.get("addressee"))
    for key in ("refer", "relations", "simile"):
        for entry in lock_scene.get(key, []):
            for field in ("subj", "obj", "vehicle", "phrase", "resolves"):
                if field in entry:
                    add(entry[field])
    for field in ("location", "region"):
        add(lock_scene.get(field))
    for c in lock_scene.get("cohort", []):
        add(c)
    return terms


def mark_italian(text, terms):
    """Wrap each licensed lock term occurring in the English digest in *asterisks* (Markdown italic),
    so embedded Italian names and epithets are visually distinct (in Japanese the Latin script already
    sets them apart). Deterministic — driven by the closed lock vocabulary, so this is a code-side
    mechanical normalization, not a prompt instruction. Longest term first (regex alternation is
    left-greedy) so a multi-word epithet wraps whole; the `[*\\w]` boundary makes it idempotent (a
    term already inside asterisks is not re-wrapped) and keeps a term from matching inside a word."""
    terms = sorted({t for t in terms if t}, key=len, reverse=True)
    if not terms:
        return text
    pattern = re.compile(r"(?<![*\w])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![*\w])",
                         re.IGNORECASE)
    return pattern.sub(lambda m: f"*{m.group(0)}*", text)


def digest_scene(canto, canto_title, s, e, scene_name, tagged, reading, lock_scene, prior,
                 model, include_thoughts):
    """One scene's bilingual digest: English from (replayed reading + lock vocabulary), then Japanese
    translated from that English with names kept in source spelling. Returns (en, ja)."""
    step_sep("digest en")
    messages = [
        {"role": "user", "content": build_reason_prompt(canto, canto_title, s, e, scene_name,
                                                         tagged, "", "")},
        {"role": "assistant", "content": reading},
        {"role": "user", "content": build_digest_prompt(scene_name, s, e, lock_scene, prior)},
    ]
    en = call_llm(messages, model, include_thoughts=include_thoughts).text.strip()
    if not en:
        print(f"Error: digest generation produced no English prose for scene {s}-{e} "
              f'"{scene_name}" after {LLM_RETRIES} attempts; aborting (rerun to retry).',
              file=sys.stderr)
        sys.exit(1)

    step_sep("digest ja")
    ja = call_llm([{"role": "user", "content": build_digest_translate_prompt(en, lock_names(lock_scene))}],
                  model, include_thoughts=include_thoughts).text.strip()
    if not ja:
        print(f"Error: digest translation produced no Japanese for scene {s}-{e} "
              f'"{scene_name}" after {LLM_RETRIES} attempts; aborting (rerun to retry).',
              file=sys.stderr)
        sys.exit(1)
    return en, ja


def prior_digest(path):
    """The English digest sentences of scenes already in this canto's file, as continuity context
    for the next scene (one `- ` line per finished scene, in order)."""
    out = []
    for _s, _e, block in iter_scene_blocks(path):
        for line in block.splitlines():
            if line.startswith("en:"):
                out.append(f"- {line[len('en:'):].strip()}")
    return "\n".join(out)


def digest_canto(canticle, canto, model, include_thoughts):
    """Generate one canto's digest, scene by scene. The output file (NN.txt) is the checkpoint: each
    finished scene is written as it completes and skipped on resume."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    readings = load_readings(canticle, canto)
    locks = lock_by_scene(canticle, canto)
    all_whos = [fig["who"] for sc in locks.values() for fig in sc.get("cast", [])]
    path = out_path(OUT_DIR, canticle, canto)

    done = complete_scene_ends(path)
    blocks = [f"{block}\n" for _s, e, block in iter_scene_blocks(path) if e in done]

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        if (s, e) not in readings or not readings[(s, e)]:
            print(f"Error: no committed reading for scene {s}-{e} (run 03-reading first).",
                  file=sys.stderr)
            sys.exit(1)
        if (s, e) not in locks:
            print(f"Error: no 14-lock entry for scene {s}-{e} (run 14-lock first).", file=sys.stderr)
            sys.exit(1)
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        tagged, _k, _meta = number_scene(lines, s, e)
        en, ja = digest_scene(canto, canto_title, s, e, scene_name, tagged, readings[(s, e)],
                              locks[(s, e)], prior_digest(path), model, include_thoughts)
        # Translation above ran on the clean English; mark the embedded Italian for STORAGE only.
        en = mark_italian(en, scene_terms(locks[(s, e)], all_whos))
        blocks.append(render_scene_block(s, e, scene_name, f"en: {en}\nja: {ja}"))
        append_canto(path, canto, canto_title, blocks)
        print(f"saved scene {s}-{e} to {path}")

    print(f"\nCanto {canto} written to {path}")


def remark_canto(canticle, canto):
    """Re-mark the embedded Italian terms of an already-committed canto digest with *asterisks*, in
    place (pure code, no LLM). Idempotent — a term already wrapped is left as is. Returns the number
    of scenes rewritten, or None if the canto has no committed digest."""
    path = out_path(OUT_DIR, canticle, canto)
    if not path.exists():
        return None
    canto_title, scenes = load_scenes(canticle, canto)
    locks = lock_by_scene(canticle, canto)
    all_whos = [fig["who"] for sc in locks.values() for fig in sc.get("cast", [])]
    digest = load_digest(canticle, canto)

    blocks = []
    for s, e, scene_name in scenes:
        body = digest.get((s, e))
        if not body or (s, e) not in locks:
            continue
        en = mark_italian(body.get("en", ""), scene_terms(locks[(s, e)], all_whos))
        blocks.append(render_scene_block(s, e, scene_name, f"en: {en}\nja: {body.get('ja', '')}"))
    append_canto(path, canto, canto_title, blocks)
    return len(blocks)


def cmd_remark(canticle, only_canto):
    cantos = [only_canto] if only_canto is not None else available_cantos(canticle)
    for canto in cantos:
        n = remark_canto(canticle, canto)
        if n is not None:
            print(f"remark {canticle} {canto:02d}: {n} scenes re-marked")


def cmd_run(canticle, model, only_canto, include_thoughts):
    cantos = available_cantos(canticle)
    if not cantos:
        print(f"Error: no markup for {canticle} (run markup.py first)", file=sys.stderr)
        sys.exit(1)
    if only_canto is not None:
        if only_canto not in cantos:
            print(f"Error: Canto {only_canto} not found for {canticle}", file=sys.stderr)
            sys.exit(1)
        targets = [only_canto]
    else:
        targets = cantos

    for canto in targets:
        path = out_path(OUT_DIR, canticle, canto)
        if path.exists():
            _, scenes = load_scenes(canticle, canto)
            if complete_scene_ends(path) >= {e for _, e, _ in scenes}:
                print(f"Canto {canto}: already complete at {path}, skipping.")
                continue
        digest_canto(canticle, canto, model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Bilingual digest per scene for Dante's Divina Commedia, constrained to the "
                    "14-lock identity/setting vocabulary (the lock's first consumer; see "
                    "15-digest/README.md).")
    parser.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"LLM for generation (default: {DEFAULT_MODEL})")
    parser.add_argument("-c", "--canto", type=int,
                        help="Process only this canto. The output file (NN.txt) is the checkpoint; "
                             "delete it to regenerate a completed canto.")
    parser.add_argument("--no-think", action="store_true",
                        help="Disable chain-of-thought (CoT is ON by default for this pass).")
    parser.add_argument("--remark", action="store_true",
                        help="Re-mark embedded Italian terms in already-committed digests with "
                             "*asterisks* (pure code, no LLM); does not regenerate.")
    args = parser.parse_args()

    for canticle in args.canticles:
        if args.remark:
            cmd_remark(canticle, args.canto)
        else:
            cmd_run(canticle, args.model, args.canto, not args.no_think)


if __name__ == "__main__":
    main()
