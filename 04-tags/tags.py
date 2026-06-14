"""
Identity-first per-tag resolution for Dante's Divine Comedy (analysis step, pre-processing).

Names every numbered person-reference of a scene: one `n. Name` line per tag, where Name is
the MOST SPECIFIC identification the committed reading establishes, in SOURCE (Italian)
spelling. This is the authoritative channel the downstream passes consume.

Identity-first (the change from the old 05-tags). The old epithet rule committed `anima`
where the reading said "specifically Beatrice" and `Poeta` where it said Virgil — data
strictly poorer than the reading it was built from. Here a figure the reading identifies by
proper name gets that name (`Beatrice`, `Virgilio`) even when this scene's text has not
uttered it; only a figure the reading itself tracks by epithet alone (a beast, a simile
figure, a generic) keeps the source-text epithet. The tag's SURFACE form is not the model's
job at all — `number_scene`'s meta carries it, so code can pair surface with identity
mechanically.

It binds DIRECTLY to the committed reading. WHO drift used to leak from a re-expression
layer into the resolution; resolving straight from the reading removes that path, and the
turn is narrowed so the model cannot re-decide WHO — it only enumerates and spells.

Pipeline position:
    markup.py  -> every person-reference marked, numbered by scenelib
    reading.py -> a free prose reading per scene             [committed, no check]
    tags.py    -> `n. Name` identity resolution (this)       [structure-checked, reader model]
    (downstream) registry + relations + KG assembly          [not yet built]

One generation pass (`-m`, the larger Gemma reader) per scene, two turns over one conversation:
      Turn 1  the committed reading, replayed as the assistant's reasoning turn.
      Turn 2  the resolution table, one numbered `n. Name` line per tag — line n is tag [n]
              (a plain numbered list, NOT bracketed, so it doesn't reuse the tags' own
              `[..]`/`{..}` delimiters).
Chain-of-thought is ON by default (`--no-think` disables it): naming a tag is judgment-heavy
coreference, so the extra deliberation helps; the runaway guard (scenelib.call_llm) covers the
added risk, and Ollama routes the thinking to its own channel so resp.text stays clean
. Turn 2 is checked (every tag named once, none extra/empty, no pronoun echoed)
and retried on failure; the reply is normalized with scenelib.unbrace first.

Orthography is code's job, not the model's: every parsed label runs through
scenelib.fix_elision BEFORE the check and BEFORE the rendered table re-enters the
conversation history — the old 05-tags prompt clause that asked the model
to correct elisions over-corrected (`l'altra` -> `la altra`) and is gone.

The output is PLAIN TEXT, not JSON (memory gemma-cot-plaintext). The interpretation the check
cannot verify (is [4] really Beatrice?) is inherited from the reading and ships as generated
(no hand-proofreading).

Input:  02-markup/<canticle>/NN.txt             (markup.py final output; run it first)
        03-reading/<canticle>/NN.txt            (reading.py prose; run it first)
        scene ranges + names                 (from the dante_corpus API)
Output: 04-tags/<canticle>/NN.txt               (committed, hand-editable). Per scene a
        `## Scene s-e: name` block of `n. Name` lines. The file is the checkpoint: a scene
        already present is skipped, so an interrupted run resumes. Delete to regenerate.
"""
import argparse
import re
import sys

from dante_analyze import (
    TAGS_DIR, READING_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup,
    load_readings, number_scene, unbrace, fix_elision, call_llm, step_sep,
    build_reason_prompt, out_path, done_scene_ends, restore_blocks, render_scene_block,
    append_canto,
)

OUT_DIR = TAGS_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # the stronger reader (judgment-heavy coreference)


# ---------- reply parsing & check ----------

RESOLVE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")


def parse_resolution(text):
    """{tag_no: name} from the numbered 'n. Name' lines of a reply (last wins on dup).
    Line number n is tag [n]; a plain numbered list is used (not bracketed `[n] =`) so the
    resolution doesn't reuse the `[..]`/`{..}` delimiters that mark the tags themselves.
    Every label passes through fix_elision here — a mechanical repair code owns
, applied before the check and before the rendered table re-enters
    the conversation history, so the model never sees its own un-elided quirk."""
    out = {}
    for raw in text.splitlines():
        m = RESOLVE_RE.match(raw)
        if m:
            out[int(m.group(1))] = fix_elision(m.group(2))
    return out


def _is_echo(name, surface):
    """True when a resolution `name` merely repeats the pronoun `surface` instead of
    naming a person (apostrophes/case ignored, e.g. `i'` vs `Io`)."""
    norm = lambda x: x.strip().strip("'").lower()
    return norm(name) == norm(surface)


def check_tags(resolution, k, tagmeta):
    """Check the resolution of a scene with tags 1..k. Returns a list of problems (empty = OK):
    every tag named exactly once, nothing extra or empty, and a pronoun tag resolved to a NAME
    rather than echoed verbatim. Proves STRUCTURE only — whether the name is the RIGHT person is
    interpretation, inherited from the reading and shipped as generated."""
    problems = []
    expected = set(range(1, k + 1))
    for n in sorted(resolution):
        if n not in expected:
            problems.append(f"names unknown tag [{n}] (scene has tags 1-{k})")
        elif not resolution[n].strip():
            problems.append(f"tag [{n}] is empty")
        elif tagmeta.get(n, ("", ""))[0] == "pron" and _is_echo(resolution[n], tagmeta[n][1]):
            problems.append(f"tag [{n}] is the pronoun '{resolution[n]}', not a person's name")
    for n in sorted(expected - set(resolution)):
        problems.append(f"missing tag [{n}]")
    return problems


# ---------- prompts ----------

def build_resolution_prompt(k):
    """The reading is already in the conversation verbatim (replayed as the assistant's
    reasoning turn) and it ALREADY established who each tag refers to, so this turn does NOT
    re-decide the referent — it enumerates the reading's identifications, identity-first: the
    most specific identification the reading gives, in source spelling. No orthography
    correction is requested (fix_elision runs in code); no surface-form preservation is
    requested (number_scene's meta carries the surface)."""
    return f"""Give the resolution table for the scene above: for EVERY tag from [1] to [{k}], one
numbered line

    n. Name

where line number n names the PERSON or being that tag `[n]` refers to (line 1 is tag [1],
line 2 is tag [2], …). Use a PLAIN NUMBERED LIST (`1.`, `2.`, …) — do NOT bracket the number,
since `[..]`/`{{..}}` are the tags' own markup and the resolution should not reuse them.

This is an ENUMERATION of your reading above, NOT a re-interpretation: the reading already
established who each tag is, and that identification is FIXED. KEEP it exactly — do NOT change
who a tag refers to, do NOT swap a person for an abstraction, and do NOT downgrade any of them
to `(unknown)`.

For each tag, write the MOST SPECIFIC identification the reading gives, in SOURCE (Italian)
spelling:
- If the reading identifies the figure by a PROPER NAME — even one this scene's text has not
  uttered yet — use that proper name, in the spelling the work itself uses, never the English
  exonym.
- If the reading tracks the figure only by an EPITHET or periphrasis (a personification, a
  beast, a simile figure, a generic "anyone"), use that source-text epithet — the exact words
  the text uses — and use the SAME label for every tag referring to it in this scene.
- If one tag covers SEVERAL figures at once, name them all on its one line, separated by
  commas.

NEVER echo the pronoun itself — `1. io`, `2. mi`, `3. i'` are all wrong; a tag must resolve to a
referent (the first-person narrator is `Dante`).

Reserve `(unknown)` only for a tag the reading itself left unidentified.

Output exactly one numbered line `n. Name` for each tag from 1 to {k}, and nothing else."""


def build_retry_prompt(problems, k):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The resolution did not pass the check:
{issues}

Produce it again, fixing these problems. Output one numbered line `n. Name` for every tag from
1 to {k} (line n = tag [n]; a plain numbered list, not bracketed), and nothing else. Every tag
1-{k} must be named exactly once; do not name any tag outside 1-{k}. A resolution names the
most specific identification the reading gives, in SOURCE spelling, never the pronoun itself
(`1. io` is wrong; the first-person narrator is `Dante`). If a flagged pronoun's referent
genuinely cannot be identified, write `n. (unknown)` rather than repeating the pronoun word."""


# ---------- per-scene driver ----------

def tags_scene(canto, canto_title, s, e, scene_name, tagged, k, tagmeta, reading,
               model, include_thoughts, max_attempts):
    """Produce one scene's resolution table with `model`, gated by the check. Two turns over
    one conversation: the committed reading is replayed as the assistant's reasoning turn (built
    on the same reason prompt, no cross-canto context), then the table — an identity-first
    enumeration of the WHO the reading already fixed (still in context), not a re-derivation.
    `include_thoughts` toggles chain-of-thought (on by default; see module docstring). Returns
    resolution_text, keeping the last draft even if unresolved (flagged by caller)."""
    if k == 0:
        # No person-references in this scene: the resolution table is empty by
        # construction (check_tags passes on `{}` when k==0). Skip generation —
        # otherwise the model is asked for tags [1]..[0], correctly returns nothing,
        # and that empty reply needlessly trips call_llm's runaway/empty guard.
        print(f"tags scene {s}-{e}: no tags, skipping generation", file=sys.stderr)
        return ""

    reason = build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, "", "")
    messages = [{"role": "user", "content": reason},
                {"role": "assistant", "content": reading},
                {"role": "user", "content": build_resolution_prompt(k)}]

    step_sep("tags resolution")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    resolution_text = _render(parse_resolution(unbrace(resp.text)))
    return _resolve(s, e, k, tagmeta, resolution_text, messages, model, include_thoughts,
                    max_attempts)


def _render(resolution):
    """The `n. Name` lines for a parsed resolution dict, in tag order."""
    return "\n".join(f"{n}. {resolution[n]}" for n in sorted(resolution))


def _resolve(s, e, k, tagmeta, resolution_text, messages, model, include_thoughts, max_attempts):
    """Check `resolution_text`, retrying in-conversation until it passes or `max_attempts`
    is hit; the last draft is kept (flagged) if it never does."""
    for attempt in range(1, max_attempts + 1):
        problems = check_tags(parse_resolution(resolution_text), k, tagmeta)
        if not problems:
            print(f"tags scene {s}-{e}: OK — all {k} tag(s) resolved", file=sys.stderr)
            return resolution_text
        print(f"tags scene {s}-{e}: attempt {attempt}/{max_attempts}: "
              f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": resolution_text},
            {"role": "user", "content": build_retry_prompt(problems, k)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        resolution_text = _render(parse_resolution(unbrace(resp.text)))
    print(f"tags scene {s}-{e}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping last draft (flagged)", file=sys.stderr)
    return resolution_text


# ---------- canto driver ----------

def tags_canto(canticle, canto, gen_model, include_thoughts, max_attempts=3):
    """Resolve one canto's tags, scene by scene, each scene replaying its committed reading.
    The output file (NN.txt) is the checkpoint: each finished scene is written as it completes
    and skipped on resume."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    readings = load_readings(canticle, canto)
    path = out_path(OUT_DIR, canticle, canto)

    done = done_scene_ends(path)
    blocks = restore_blocks(path)

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        reading = readings.get((s, e))
        if not reading:
            print(f"Error: no reading for scene {s}-{e} in {out_path(READING_DIR, canticle, canto)}"
                  f" (run reading.py first)", file=sys.stderr)
            sys.exit(1)
        tagged, k, tagmeta = number_scene(lines, s, e)
        resolution = tags_scene(canto, canto_title, s, e, scene_name, tagged, k, tagmeta,
                                reading, gen_model, include_thoughts, max_attempts)
        blocks.append(render_scene_block(s, e, scene_name, resolution))
        append_canto(path, canto, canto_title, blocks)
        print(f"saved scene {s}-{e} to {path}")

    print(f"\nCanto {canto} written to {path}")


def cmd_run(canticle, gen_model, only_canto, include_thoughts):
    cantos = available_cantos(canticle)
    if not cantos:
        print(f"Error: no markup for {canticle} (run markup.py first)", file=sys.stderr)
        sys.exit(1)
    if only_canto is not None:
        if only_canto not in cantos:
            print(f"Error: Canto {only_canto} not found for {canticle} "
                  f"(no markup output for canto {only_canto:02d})", file=sys.stderr)
            sys.exit(1)
        targets = [only_canto]
    else:
        targets = cantos

    for canto in targets:
        path = out_path(OUT_DIR, canticle, canto)
        if path.exists():
            _, scenes = load_scenes(canticle, canto)
            if done_scene_ends(path) >= {e for _, e, _ in scenes}:
                print(f"Canto {canto}: already complete at {path}, skipping.")
                continue
        tags_canto(canticle, canto, gen_model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Identity-first per-tag resolution for Dante's Divina Commedia: per-scene "
                    "`n. Name` table, bound to the committed reading (see 04-tags/README.md).")
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
