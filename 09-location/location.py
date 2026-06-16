"""
Location pass for Dante's Divina Commedia (context-lock Step 1): per-scene LOCAL SETTING —
where each scene physically is, in the work's own terms. The action-only KG (08-kg) carries no
setting; this is the first pass that supplies the missing where-layer, and the per-scene location
SURFACES it emits are what 10-topography will fold into canonical regions (mirroring 04-tags
surface -> 05-registry canonical).

A single text-derived judgment over the SOURCE. Unlike tags.py/relations.py it replays no
committed reading and uses no tags: it reads the plain source lines (numbered) plus the SETTING
SO FAR carried from earlier scenes, and asks only where the scene is set.

CURRENT SETTING ONLY. A place merely named, described, prophesied, or compared (Hell while the
scene is still on the slope, Italy, the gate of St. Peter) is NOT the setting — it is a
referred-to place that belongs to a later referent layer, excluded here.

NO EXTERNAL CANON (repository premise). The prompt never names the poem's known geography
(circles, terraces, spheres); only the place words the text itself uses. That known structure is
10-topography's EVALUATION target, not an input.

Output line grammar (one per location; a scene may list more than one for in-scene movement, the
first being the primary current setting):
      - it: <source place term> | en: <english gloss> | basis: <s>[-<e>]
`it` is the text's own place noun/phrase (`-` when the setting is purely carried and the scene
states no place word of its own); `en` a short English gloss; `basis` the source line number(s)
within the scene that support the setting. The full quote is recoverable from the line refs at
lock-assembly time (13-lock), so the checkable core is a line reference, not a fragile string.

Chain-of-thought is ON by default (`--no-think` disables); same justification as reading.py
(the where-reasoning runs in Ollama's own thinking channel, `resp.text` is the location lines,
call_llm caps runaway). The per-scene structural check guards STRUCTURE only — well-formed lines,
non-empty gloss, basis within the scene; whether the named place is the RIGHT one is
interpretation, shipped as generated (no hand-proofreading).

Input:  02-markup/<canticle>/NN.txt (source lines), scene ranges (01-scenes JSON via load_scenes).
Output: 09-location/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of location lines,
        plus a trailing `# recap` carrying the canto's final setting to the next canto (the file
        is the checkpoint: a finished scene is skipped on resume; delete to regenerate).
"""
import argparse
import re
import sys

from dante_analyze import (
    LOCATION_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup, strip_to_source,
    call_llm, step_sep, out_path, done_scene_ends, read_recap, restore_blocks, scene_bodies,
    render_scene_block, append_canto,
)

OUT_DIR = LOCATION_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # the stronger reader (judgment-heavy setting)


# ---------- reply parsing & check ----------

# A location line: "- it: <term> | en: <gloss> | basis: s[-e]". The `-e` is optional (a one-line
# basis may be written `basis: 17`), normalized back to the two-number form by _render.
LOCATION_RE = re.compile(
    r"^-\s*it:\s*(?P<it>.*?)\s*\|\s*en:\s*(?P<en>.*?)\s*\|\s*"
    r"basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)
# An intended-but-malformed location line: starts like one (`- `) but fails the grammar.
LOC_PREFIX_RE = re.compile(r"^-\s+\S")


def parse_locations(text):
    """Parse a reply into (locs, malformed). `locs` is a list of {it, en, start, end} dicts in
    file order; `malformed` is the list of raw lines that LOOK like a location (`- …`) but do not
    match the grammar. Malformed lines are surfaced (not silently dropped) so a garbled line cannot
    make the check pass spuriously."""
    locs, malformed = [], []
    for raw in text.splitlines():
        m = LOCATION_RE.match(raw)
        if m:
            start = int(m.group("bs"))
            locs.append({
                "it": m.group("it").strip(),
                "en": m.group("en").strip(),
                "start": start,
                "end": int(m.group("be")) if m.group("be") else start,
            })
        elif LOC_PREFIX_RE.match(raw):
            malformed.append(raw.strip())
    return locs, malformed


def check_locations(locs, malformed, s, e):
    """Check a scene's locations (line range s..e). Returns a list of problems (empty = OK). The
    structural invariants: at least one well-formed line, a non-empty gloss on each, and every
    basis range within the scene. Structure only — whether the place is the right one is
    interpretation, shipped as generated."""
    problems = []
    for line in malformed:
        problems.append(f"malformed location line (does not match the grammar): {line}")
    if not locs:
        problems.append("no location line (every scene has a current setting; give at least one)")
    for loc in locs:
        tag = f"it: {loc['it']!r}"
        if not loc["en"]:
            problems.append(f"{tag}: empty `en` gloss")
        if not s <= loc["start"] <= loc["end"] <= e:
            problems.append(f"{tag}: basis {loc['start']}-{loc['end']} is outside the scene {s}-{e}")
    return problems


# ---------- prompts ----------

def _numbered_source(lines, s, e):
    """The scene's plain source, each line prefixed with its source line number, so the model can
    cite a correct `basis` and the checker can validate it."""
    return "\n".join(f"{ln} {strip_to_source(lines[ln - 1])}" for ln in range(s, e + 1))


def build_location_prompt(canto, canto_title, s, e, scene_name, source, carried):
    """The single generation turn: name where THIS scene is physically set, over its numbered
    source plus the setting carried from earlier scenes. Examples are schematic only — never a
    location drawn from the scene under test (no answer leakage)."""
    ctx = ""
    if carried:
        ctx = (f"\nThe setting established so far (carried from earlier scenes — a scene that does "
               f"not restate its place inherits the previous one):\n\n{carried}\n")
    return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

This is Canto {canto} — "{canto_title}". Here is scene "{scene_name}" (lines {s}-{e}), one source
line per number:
{ctx}
```
{source}
```

Identify WHERE THIS SCENE PHYSICALLY TAKES PLACE — the current setting, the place the characters
are actually in during these lines.

Rules:
- CURRENT SETTING ONLY. A place that is merely NAMED, described, foretold, recalled, or used in a
  comparison is NOT the setting. (If, while standing in one place, a character speaks of another
  place — somewhere they will go, a place far off, a realm described — that other place is NOT this
  scene's setting; leave it out.)
- DERIVE IT FROM THE TEXT. Use only the place words this poem itself uses. Do NOT name any
  external or systematic geography the text does not state in these lines; do NOT label the place
  with a category from outside the words on the page.
- A scene that states no place of its own INHERITS the setting carried above — repeat it, and set
  `it` to `-` since this scene gives no source term.
- If the scene MOVES from one place to another within these lines, list each place on its own line,
  the place the scene starts in FIRST.

Output one line per place, in exactly this form:

    - it: <source term> | en: <english gloss> | basis: x-y

where `it` is the place word(s) AS THE TEXT WRITES THEM (or `-` if the scene states none and the
setting is carried), `en` is a short English gloss of the place, and `x-y` are the source line
number(s) within {s}-{e} that show the setting (for a single line, write it once, e.g. `basis: {s}`).

Output only location lines, one per place, and nothing else.

Schematic examples of the FORM only (not from this scene):
    - it: <place word> | en: a short gloss | basis: x-y
    - it: - | en: the carried setting, unchanged | basis: x-y"""


def build_retry_prompt(problems, s, e):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The location list did not pass the check:
{issues}

Produce it again, fixing these problems. Each line is

    - it: <source term> | en: <english gloss> | basis: x-y

with at least one line, a non-empty `en` gloss, and `x-y` within {s}-{e} (x ≤ y). `it` is the
place word(s) as the text writes them, or `-` if the scene states none and the setting is carried.
Output only location lines and nothing else."""


# ---------- per-scene driver ----------

def _render(locs):
    """The canonical location lines for parsed locs, in file order (well-formed lines only, so the
    committed file never carries malformed drafts)."""
    return "\n".join(
        f"- it: {loc['it']} | en: {loc['en']} | basis: {loc['start']}-{loc['end']}"
        for loc in locs
    )


def location_scene(canto, canto_title, s, e, scene_name, source, carried,
                   model, include_thoughts, max_attempts):
    """Produce one scene's location list with `model`, gated by the structural check. A single
    generation turn (the where-reasoning runs in the thinking channel), retried in-conversation
    until it passes or `max_attempts` is hit; the last draft is kept (flagged) if it never does."""
    messages = [{"role": "user",
                 "content": build_location_prompt(canto, canto_title, s, e, scene_name,
                                                  source, carried)}]
    step_sep("location")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    draft = resp.text
    for attempt in range(1, max_attempts + 1):
        locs, malformed = parse_locations(draft)
        problems = check_locations(locs, malformed, s, e)
        if not problems:
            print(f"location scene {s}-{e}: OK — {len(locs)} place(s)", file=sys.stderr)
            return _render(locs)
        print(f"location scene {s}-{e}: attempt {attempt}/{max_attempts}: "
              f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": build_retry_prompt(problems, s, e)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        draft = resp.text
    print(f"location scene {s}-{e}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping last draft (flagged)", file=sys.stderr)
    return _render(parse_locations(draft)[0])


# ---------- carry-forward ----------

def _summarize(locs):
    """One-line setting summary from a scene's parsed locations (the last place is where the scene
    leaves off), e.g. "the slope (erta)" / "the dark wood (selva oscura)"; "" if none."""
    if not locs:
        return ""
    loc = locs[-1]
    return f"{loc['en']} ({loc['it']})" if loc["it"] and loc["it"] != "-" else loc["en"]


def _carried_text(prior, recap):
    """The SETTING SO FAR block: prior scenes of this canto (`prior` = [(s, e, summary), …]) under
    the previous canto's `recap`. Empty string when nothing is carried yet."""
    parts = []
    if recap:
        parts.append(recap)
    parts += [f"- scene {s}-{e}: {summ}" for s, e, summ in prior if summ]
    return "\n".join(parts)


# ---------- canto driver ----------

def location_canto(canticle, canto, gen_model, include_thoughts, max_attempts=3):
    """Build one canto's locations, scene by scene, each scene carrying the settings established so
    far. The output file (NN.txt) is the checkpoint: each finished scene is written as it completes
    and skipped on resume; a trailing `# recap` carries the canto's final setting forward."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    path = out_path(OUT_DIR, canticle, canto)

    done = done_scene_ends(path)
    blocks = restore_blocks(path)
    # carry the previous canto's final setting in as the opening context
    prev = out_path(OUT_DIR, canticle, canto - 1)
    recap = read_recap(prev) if canto > 1 else ""

    # rebuild the running setting summary from whatever is already committed (resume-safe)
    prior = [(s, e, _summarize(parse_locations(body)[0]))
             for (s, e), body in scene_bodies(path).items()]

    # whole-canto source (lowercased), for the soft `it`-in-source warning
    canto_src = " ".join(strip_to_source(ln) for ln in lines).lower()

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")
    last_summary = prior[-1][2] if prior else recap
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        source = _numbered_source(lines, s, e)
        carried = _carried_text(prior, recap)
        body = location_scene(canto, canto_title, s, e, scene_name, source, carried,
                              gen_model, include_thoughts, max_attempts)
        locs, _ = parse_locations(body)
        for loc in locs:  # soft check: a stated `it` term should occur in the canto source
            it = loc["it"]
            if it and it != "-" and it.lower() not in canto_src:
                print(f"  note: `it` term {it!r} not found verbatim in the canto source "
                      f"(may be paraphrased or carried)", file=sys.stderr)
        summ = _summarize(locs)
        prior.append((s, e, summ))
        if summ:
            last_summary = summ
        blocks.append(render_scene_block(s, e, scene_name, body))
        append_canto(path, canto, canto_title, blocks,
                     recap=f"Final setting: {last_summary}" if last_summary else None)
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
        location_canto(canticle, canto, gen_model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Location pass for Dante's Divina Commedia: per-scene local setting (current "
                    "place only), derived from the source, carried scene to scene.")
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
