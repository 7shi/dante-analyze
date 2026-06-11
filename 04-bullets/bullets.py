"""
Scene "who did what" bullets for Dante's Divine Comedy (analysis step, pre-processing).

Recasts each scene as a plain English bullet list whose items cite the numbered
person-references they cover. It consumes the committed prose reading from reading.py
(the free interpretation) and re-grounds it to the NUMBERED TAGS so a logic check can
prove faithfulness of COVERAGE — every tag cited by some bullet, none invented.

This pass is ONLY the bullets. Naming each tag in SOURCE spelling (the `n. Name`
resolution table) is a different, harder job — judgment-heavy coreference rather than
fluent recast — so it is split into its own pass, tags.py, which binds directly to the
reading and runs a stronger reader model (ARCHITECTURE §11/§13). The bullets here are a
NON-authoritative working layer: their surface names may anglicize freely ("Virgil"),
because the authoritative source-spelling data comes from tags.py, not this prose.

Pipeline position:
    markup.py  -> every person-reference marked, numbered by scenelib
    reading.py -> a free prose reading per scene             [committed, no check]
    bullets.py -> tag-citing English bullets (this)          [coverage-checked, fast model]
    tags.py    -> `n. Name` source-spelling resolution       [reader model]

Tagging (deterministic, no LLM; scenelib.number_scene). For each scene the marks
already present in NN-4 (`[..]`/`[+..]` pronouns, `{..}` names) are numbered 1..k in
order of appearance, the number spliced in after the opening delimiter:
    rispuos'[+io] [io] [lui] con {vergognosa fronte}.
 -> rispuos'[1:+io] [2:io] [3:lui] con {4:vergognosa fronte}.
A bullet refers to a tag by its bare number in brackets, `[1]`, regardless of the
mark's original delimiter.

One generation pass (`-m`) per scene, two turns over one conversation:
      Turn 1  the committed reading, replayed as the assistant's reasoning turn.
      Turn 2  the "who did what" bullets, explicit subjects, each citing its tags `[n]`.
Chain-of-thought is ON by default (`--no-think` disables it): on the reader model the extra
deliberation improves the bullet reconstruction, the runaway guard (scenelib.call_llm) covers
the added runaway risk, and Ollama routes the thinking to its own channel so resp.text stays
clean (ARCHITECTURE §1). Turn 2 is coverage-checked (every tag cited, none invented, no junk
bracket) and retried on failure.

Each reply is mechanically normalized (scenelib.unbrace) before it is parsed OR appended
to the conversation: `{`/`}` -> `[`/`]` (the model often cites a name tag with its source
brace, `{4}`, instead of `[4]`) and backtick wrapping is dropped, so `[n]` is the one
citation form. The NORMALIZED text — not the raw reply — goes back into the history, so the
model never sees its own `{4}` / `` `[1]` `` in a prior turn and keeps echoing it across turns
(ARCHITECTURE §12). That is the mechanical half; a bracket holding anything but a bare number
(`[no tag]`, `[]`) is a substantive slip, so it is left in place for the coverage check to
flag and the model to fix on retry — not silently deleted.

WHO each tag refers to is NOT decided here — the bullets just re-express the reading already
in context; the authoritative identification is tags.py's job. The interpretation a coverage
check cannot verify is hand-proofread (on the reading and on this output).

The output is PLAIN TEXT, not JSON: a local Gemma runs away on long structured output
(memory gemma-cot-plaintext), and the `[n]` reference form is enough to extract mechanically.

Input:  02-markup/<canticle>/NN-4.txt            (markup.py final output; run it first)
        03-reading/<canticle>/NN.txt             (reading.py prose; run it first)
        scene ranges + names                  (from the dante_corpus API)
Output: 04-bullets/<canticle>/NN.txt             (committed, hand-editable). Per scene a
        `## Scene s-e: name` block of bullets. The file is the checkpoint: a scene already
        present is skipped, so an interrupted run resumes. Delete the file to regenerate.
"""
import argparse
import re
import sys

from dante_analyze import (
    BULLETS_DIR, READING_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup,
    load_readings, number_scene, parse_bullets, unbrace, call_llm, step_sep,
    build_reason_prompt, out_path, done_scene_ends, restore_blocks, render_scene_block,
    append_canto,
)

OUT_DIR = BULLETS_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # bullets need WHO judgment + pronoun control (26B MoE drifted)


# ---------- reply parsing & coverage check ----------

# a bullet's tag citation, `[n]`. The reply is run through unbrace() first, so a name tag the
# model cited with its source brace (`{4}`) is already `[4]` by the time anything reads it.
TAGREF_RE = re.compile(r"\[(\d+)\]")
# any (non-nested) `[...]` group — used to tell a real `[n]` citation from junk like `[no tag]`.
BRACKET_GROUP_RE = re.compile(r"\[[^\[\]]*\]")


def clean_bullet(b):
    """Collapse a bullet's stray whitespace before it is committed. Bracket/backtick cosmetics
    are already normalized (the reply passed through unbrace), so a bracket group with NON-numeric
    content (`[]`, `[no tag]`, `[3 is not present here ...]`) is LEFT IN PLACE for the coverage
    check to flag and the model to fix — it is not silently deleted."""
    return re.sub(r"\s{2,}", " ", b).strip()


def cited_tags(bullets):
    """All tag numbers referenced as `[n]` across the bullet list."""
    tags = set()
    for b in bullets:
        tags.update(int(n) for n in TAGREF_RE.findall(b))
    return tags


def junk_citations(bullets):
    """`[...]` groups in the bullets that are NOT a bare `[n]` tag citation — e.g. `[]`,
    `[no tag]`, `[3 is not present here ...]`. Round-paren asides like `(God)` are not brackets
    and are left alone. Used by the coverage check to flag them for the model to fix, instead of
    clean_bullet deleting them."""
    out = []
    for b in bullets:
        for m in BRACKET_GROUP_RE.finditer(b):
            if not re.fullmatch(r"\[\d+\]", m.group(0)):
                out.append(m.group(0))
    return out


def check_bullets(bullets, k):
    """Coverage check over a scene with tags 1..k. Returns a list of problems (empty = OK):
    every tag cited by at least one bullet, none cited outside the set, no junk bracket. Proves
    faithfulness of COVERAGE only — not whether the interpretation is correct (left to
    proofreading), nor the source spelling (that is tags.py's check)."""
    problems = []
    expected = set(range(1, k + 1))
    if not bullets:
        problems.append("no bullets produced")
    cited = cited_tags(bullets)
    for n in sorted(cited - expected):
        problems.append(f"a bullet cites unknown tag [{n}] (scene has tags 1-{k})")
    for n in sorted(expected - cited):
        problems.append(f"tag [{n}] is not cited by any bullet")
    for g in junk_citations(bullets):
        problems.append(f"a bullet has the non-tag bracket `{g}` — a citation must be a "
                        f"bare `[n]`; fix the tag number or remove the bracket")
    return problems


# ---------- prompts ----------

def build_bullets_prompt(s, e):
    return f"""Now write the scene as a "who did what" bullet list.

- One `- ` bullet per event or statement, in order, covering lines {s}-{e}.
- Name each subject and object explicitly. A pronoun or reflexive ("he", "she",
  "it", "himself") is allowed ONLY when its antecedent is named earlier in the SAME
  bullet and there is no other candidate it could attach to; otherwise write the
  name. Never repeat a name where a pronoun reads naturally ("Dante found himself",
  not "Dante found Dante"). Plain English.
- The reading above ALREADY established who each numbered tag refers to. Name each
  subject and object accordingly — you are RE-EXPRESSING the reading, not
  reinterpreting it: do NOT re-decide a tag's referent, and do NOT swap a person for
  an abstraction (a tag the reading read as a person/being stays that person/being).
- At the end of each bullet, cite the numbered tags it covers as `[n]` (e.g.
  `... [1] [3]`). Every tag in the scene must be cited by at least one bullet, and
  cite only tags that appear in the scene.

Output only the bullet list, nothing else."""


def build_retry_prompt(problems, s, e, k):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The bullet list did not pass the coverage check:
{issues}

Produce it again, fixing these problems. Output ONLY the `- ` bullet list covering lines
{s}-{e}, each bullet ending with the tags `[n]` it covers. Every tag 1-{k} must be cited by at
least one bullet; cite only tags in 1-{k}; a citation is a bare `[n]` with no other brackets."""


# ---------- per-scene driver ----------

def bullets_scene(canto, canto_title, s, e, scene_name, tagged, k, reading, model,
                 include_thoughts, max_attempts):
    """Produce one scene's bullets with `model`, gated by the coverage check. Two turns over
    one conversation: the committed reading is replayed as the assistant's reasoning turn (built
    on the same reason prompt, no cross-canto context — that lives in reading.py), then the
    bullets. `include_thoughts` toggles chain-of-thought (on by default; see module docstring).
    Returns bullets_text, keeping the last draft even if unresolved (flagged by caller)."""
    reason = build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, "", "")
    messages = [{"role": "user", "content": reason},
                {"role": "assistant", "content": reading},
                {"role": "user", "content": build_bullets_prompt(s, e)}]

    step_sep("bullets")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    bullets_text = "\n".join(f"- {clean_bullet(b)}" for b in parse_bullets(unbrace(resp.text)))
    return _resolve(s, e, k, bullets_text, messages, model, include_thoughts, max_attempts)


def _resolve(s, e, k, bullets_text, messages, model, include_thoughts, max_attempts):
    """Coverage-check `bullets_text`, retrying in-conversation until it passes or
    `max_attempts` is hit; the last draft is kept (flagged) if it never does."""
    for attempt in range(1, max_attempts + 1):
        problems = check_bullets(parse_bullets(bullets_text), k)
        if not problems:
            print(f"bullets scene {s}-{e}: OK — all {k} tag(s) covered", file=sys.stderr)
            return bullets_text
        print(f"bullets scene {s}-{e}: attempt {attempt}/{max_attempts}: "
              f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": bullets_text},
            {"role": "user", "content": build_retry_prompt(problems, s, e, k)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        bullets_text = "\n".join(f"- {clean_bullet(b)}" for b in parse_bullets(unbrace(resp.text)))
    print(f"bullets scene {s}-{e}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping last draft (flagged)", file=sys.stderr)
    return bullets_text


# ---------- canto driver ----------

def bullets_canto(canticle, canto, gen_model, include_thoughts, max_attempts=3):
    """Generate one canto's bullets, scene by scene, each scene replaying its committed
    reading. The output file (NN.txt) is the checkpoint: each finished scene is written as it
    completes and skipped on resume."""
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
        tagged, k, _ = number_scene(lines, s, e)
        bullets = bullets_scene(canto, canto_title, s, e, scene_name, tagged, k, reading,
                               gen_model, include_thoughts, max_attempts)
        blocks.append(render_scene_block(s, e, scene_name, bullets))
        append_canto(path, canto, canto_title, blocks)
        print(f"saved scene {s}-{e} to {path}")

    print(f"\nCanto {canto} written to {path}")


def cmd_run(canticle, gen_model, only_canto, include_thoughts):
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
            if done_scene_ends(path) >= {e for _, e, _ in scenes}:
                print(f"Canto {canto}: already complete at {path}, skipping.")
                continue
        bullets_canto(canticle, canto, gen_model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Scene 'who did what' bullets for Dante's Divina Commedia: per-scene "
                    "tag-citing English bullets (resolution is tags.py; see PLAN.md).")
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
