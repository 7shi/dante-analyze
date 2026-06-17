"""
Addressee pass for Dante's Divina Commedia (context-lock Step 4): the ADDRESSEE of each speech span
— who the speaker is talking TO. The KG's speech edges (06-speech / 08-kg) record the SPEAKER of
every quote span but never the addressee; addressee is narrative state the action-only KG does not
carry. The lock must fix who is addressed, so this pass supplies it, the dialogue analogue of the
speaker join 06-speech already made.

CODE-FIRST, LLM only for the residual (the 06-speech method). For each attributed span, the
candidate addressees are the PRESENT cast of the span's scene (11-presence, `status: present`) minus
the speaker — a closed set already resolved upstream:

- 0 candidates  -> addressee `(none)`, source `none`. The speaker is the only present figure
  (soliloquy, or address to an absent / merely-mentioned figure). Address-to-absent is out of scope
  (the candidate pool is present-only), so it is recorded as `(none)`, not guessed.
- 1 candidate   -> that figure, source `code`. The two-person-scene case: deterministic, no LLM.
- >=2 candidates -> the LLM chooses one from the closed candidate list, source `llm`.

NO EXTERNAL CANON (repository premise). The candidate pool comes from this repo's own derived
pipeline (06-speech speakers, 11-presence cast), never external canon.

Output line grammar (one per ATTRIBUTED 06-speech span, grouped under the span's scene):
      - <quote_id> lines <s>-<e> | speaker: <name> | addressee: <name>|(none) | source: code|llm|none | basis: <bs>[-<be>]
`speaker`/`addressee` are canonical node labels (source spelling, matching the KG nodes); `source`
records how the addressee was decided; `basis` the source line range supporting it (the span lines
for the code path, the LLM-cited line for the ambiguous path). Spans whose speaker is
`(unattributed)` carry no line. A scene with no attributed span writes a `#` marker.

Chain-of-thought is ON by default (`--no-think` disables); same justification as presence.py
(addressee is a reading/coreference judgment — "use the strongest reader for coreference" — and the
output is a checked closed set, so call_llm caps runaway). The structural check guards STRUCTURE
only (the addressee is in the candidate set, the basis is within the span); whether the reading is
RIGHT is interpretation, shipped as generated (no hand-proofreading).

Input:  02-markup/<canticle>/NN.txt (source lines), scene ranges (01-scenes JSON via load_scenes),
        06-speech (attributed spans), 11-presence (present cast = the candidate pool).
Output: 12-addressee/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of addressee lines
        (the file is the checkpoint: a finished scene is skipped on resume; delete to regenerate).
"""
import argparse
import re
import sys

from dante_analyze import (
    ADDRESSEE_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup, strip_to_source,
    call_llm, step_sep, out_path, done_scene_ends, restore_blocks,
    render_scene_block, append_canto,
    load_speech, load_presence, fold_key,
)

OUT_DIR = ADDRESSEE_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # the stronger reader (addressee is reading-bound)

UNATTRIBUTED = "(unattributed)"
NONE_ADDRESSEE = "(none)"
NO_SPEECH_MARKER = "# (no attributed speech in this scene)"


# ---------- candidate pool (code) ----------

def scene_of(span, scenes):
    """The scene (s, e, name) whose line range contains the span's START line, or None. Scenes
    partition the canto, so a span begins in exactly one scene; a cross-scene span is attributed to
    where its speech begins."""
    for s, e, name in scenes:
        if s <= span["start"] <= e:
            return (s, e, name)
    return None


def present_cast(presence_figs):
    """The canonical labels a scene's 11-presence list marks `present`, in file order."""
    return [f["who"] for f in presence_figs if f["status"] == "present"]


def candidate_pool(present, speaker):
    """The present cast minus the speaker (by fold_key), preserving order — the closed set of
    figures the speaker could be addressing."""
    sp = fold_key(speaker)
    return [name for name in present if fold_key(name) != sp]


# ---------- LLM reply parsing & check ----------

# An addressee reply line: "addressee: <name> | basis: x[-y]" (leading "- " tolerated).
ADDR_REPLY_RE = re.compile(
    r"^-?\s*addressee:\s*(?P<addr>.*?)\s*\|\s*basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)
ADDR_PREFIX_RE = re.compile(r"^-?\s*addressee:")


def parse_addressee(text):
    """Parse a reply into (pick, malformed). `pick` is the first well-formed {addr, start, end} dict
    or None; `malformed` is the list of raw lines that LOOK like an addressee line but fail the
    grammar (surfaced, not dropped, so a garbled line cannot pass the check)."""
    pick, malformed = None, []
    for raw in text.splitlines():
        m = ADDR_REPLY_RE.match(raw)
        if m:
            if pick is None:
                start = int(m.group("bs"))
                pick = {
                    "addr": m.group("addr").strip(),
                    "start": start,
                    "end": int(m.group("be")) if m.group("be") else start,
                }
        elif ADDR_PREFIX_RE.match(raw):
            malformed.append(raw.strip())
    return pick, malformed


def check_addressee(pick, malformed, candidates, qs, qe):
    """Check a parsed addressee against the closed candidate set (span lines qs..qe). Returns a list
    of problems (empty = OK). Structure only — whether the reading is RIGHT is interpretation. The
    addressee matches a candidate by fold_key, so a cosmetic spelling drift is tolerated and rendered
    back to the canonical candidate label."""
    problems = []
    for line in malformed:
        problems.append(f"malformed addressee line (does not match the grammar): {line}")
    if pick is None:
        problems.append("no addressee line produced (give exactly one)")
        return problems
    cand_by_fold = {fold_key(name): name for name in candidates}
    if fold_key(pick["addr"]) not in cand_by_fold:
        problems.append(f"addressee {pick['addr']!r}: not in the candidate list {candidates} "
                        f"(choose exactly one of the listed figures)")
    if not qs <= pick["start"] <= pick["end"] <= qe:
        problems.append(f"basis {pick['start']}-{pick['end']} is outside the quote {qs}-{qe}")
    return problems


# ---------- prompts ----------

def _numbered_source(lines, s, e):
    """The scene's plain source, each line prefixed with its source line number, so the model can
    cite a correct `basis` and the checker can validate it."""
    return "\n".join(f"{ln} {strip_to_source(lines[ln - 1])}" for ln in range(s, e + 1))


def _candidate_block(candidates):
    return "\n".join(f"- {name}" for name in candidates)


def build_addressee_prompt(canto, canto_title, s, e, scene_name, source, speaker, qs, qe, candidates):
    """The single generation turn: choose, from the given candidate list, the figure the speaker is
    addressing in this quote. The candidates are the figures already resolved as PRESENT in this
    scene (minus the speaker); the model picks one, it does not invent or add a figure. Examples are
    schematic only — never a figure drawn from the scene under test (no answer leakage)."""
    return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

This is Canto {canto} — "{canto_title}". Here is scene "{scene_name}" (lines {s}-{e}), one source
line per number:

```
{source}
```

In this scene, {speaker} speaks the lines {qs}-{qe}. The following figures are PRESENT in the scene
(besides {speaker}). For this speech, decide which ONE of them {speaker} is addressing — the figure
the words are directed AT (spoken to, questioned, answered, commanded, greeted):

{_candidate_block(candidates)}

Rules:
- The addressee is the figure {speaker} is TALKING TO, not a figure merely talked ABOUT inside the
  speech. Judge from the speech and its scene.
- Choose EXACTLY ONE figure from the list above, using the name AS GIVEN. Do not add a figure that
  is not listed.

Output exactly one line, in this form:

    addressee: <name as listed> | basis: x-y

where `x-y` are the source line number(s) within {qs}-{qe} that justify the choice (for a single
line, write it once, e.g. `basis: {qs}`).

Output only that line and nothing else.

Schematic example of the FORM only (not from this scene):
    addressee: <the figure being spoken to> | basis: x-y"""


def build_retry_prompt(problems, speaker, candidates, qs, qe):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The addressee did not pass the check:
{issues}

Choose again the ONE figure {speaker} is addressing, from this list only:

{_candidate_block(candidates)}

Output exactly one line

    addressee: <name as listed> | basis: x-y

with `x-y` within {qs}-{qe} (x <= y). Use a name exactly as listed; do not add a figure. Output only
that line and nothing else."""


# ---------- per-span driver ----------

def render_line(span, addressee, source, bs, be):
    return (f"- {span['quote_id']} lines {span['start']}-{span['end']} | "
            f"speaker: {span['speaker']} | addressee: {addressee} | source: {source} | "
            f"basis: {bs}-{be}")


def addressee_span_llm(canto, canto_title, s, e, scene_name, source, span, candidates,
                       model, include_thoughts, max_attempts):
    """Resolve one ambiguous span (>=2 candidates) with `model`, gated by the structural check. A
    single generation turn (the reasoning runs in the thinking channel), retried in-conversation
    until it passes or `max_attempts` is hit; the last draft is kept (flagged) if it never does."""
    qs, qe = span["start"], span["end"]
    messages = [{"role": "user",
                 "content": build_addressee_prompt(canto, canto_title, s, e, scene_name, source,
                                                   span["speaker"], qs, qe, candidates)}]
    step_sep("addressee")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    draft = resp.text
    cand_by_fold = {fold_key(name): name for name in candidates}
    for attempt in range(1, max_attempts + 1):
        pick, malformed = parse_addressee(draft)
        problems = check_addressee(pick, malformed, candidates, qs, qe)
        if not problems:
            name = cand_by_fold[fold_key(pick["addr"])]
            print(f"addressee {span['quote_id']}: OK — {span['speaker']} -> {name}", file=sys.stderr)
            return name, pick["start"], pick["end"]
        print(f"addressee {span['quote_id']}: attempt {attempt}/{max_attempts}: "
              f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": build_retry_prompt(problems, span["speaker"], candidates, qs, qe)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        draft = resp.text
    # keep the last draft if it named a real candidate, else fall back to the first candidate.
    pick, _ = parse_addressee(draft)
    if pick and fold_key(pick["addr"]) in cand_by_fold:
        name = cand_by_fold[fold_key(pick["addr"])]
        bs, be = pick["start"], pick["end"]
    else:
        name, bs, be = candidates[0], qs, qe
    print(f"addressee {span['quote_id']}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping {name!r} (flagged)", file=sys.stderr)
    return name, bs, be


def resolve_span(canto, canto_title, s, e, scene_name, lines, span, present,
                 model, include_thoughts, max_attempts):
    """One output line for an attributed span: code where the candidate pool is 0 or 1, the LLM only
    for >=2 (the 06-speech residual method)."""
    candidates = candidate_pool(present, span["speaker"])
    if not candidates:
        return render_line(span, NONE_ADDRESSEE, "none", span["start"], span["end"])
    if len(candidates) == 1:
        return render_line(span, candidates[0], "code", span["start"], span["end"])
    source = _numbered_source(lines, s, e)
    name, bs, be = addressee_span_llm(canto, canto_title, s, e, scene_name, source, span,
                                      candidates, model, include_thoughts, max_attempts)
    return render_line(span, name, "llm", bs, be)


# ---------- canto driver ----------

def addressee_canto(canticle, canto, gen_model, include_thoughts, max_attempts=3):
    """Build one canto's addressee list, scene by scene. The output file (NN.txt) is the checkpoint:
    each finished scene is written as it completes and skipped on resume."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    spans = [sp for sp in load_speech(canticle, canto) if sp["speaker"] != UNATTRIBUTED]
    presence = load_presence(canticle, canto)
    path = out_path(OUT_DIR, canticle, canto)

    done = done_scene_ends(path)
    blocks = restore_blocks(path)

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes, "
          f"{len(spans)} attributed span(s).")
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        scene_spans = [sp for sp in spans if scene_of(sp, scenes) == (s, e, scene_name)]
        if not scene_spans:
            body = NO_SPEECH_MARKER
        else:
            present = present_cast(presence.get((s, e), []))
            out_lines = []
            for sp in scene_spans:
                if "cross-scene" in sp["flags"]:
                    print(f"  note: span {sp['quote_id']} ({sp['start']}-{sp['end']}) is "
                          f"cross-scene; attributed to its opening scene {s}-{e}", file=sys.stderr)
                out_lines.append(resolve_span(canto, canto_title, s, e, scene_name, lines, sp,
                                              present, gen_model, include_thoughts, max_attempts))
            body = "\n".join(out_lines)
        blocks.append(render_scene_block(s, e, scene_name, body))
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
        addressee_canto(canticle, canto, gen_model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Addressee pass for Dante's Divina Commedia: the addressee of each attributed "
                    "06-speech span, code for two-person scenes, LLM only when several figures are "
                    "present (candidate pool = 11-presence present cast minus the speaker).")
    parser.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"LLM for the ambiguous-span judgment (default: {DEFAULT_MODEL})")
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
