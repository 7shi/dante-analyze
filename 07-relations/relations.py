"""
Relations pass for Dante's Divine Comedy (KG Step 3): subject–predicate–object event edges per
scene. Produces the KG's EVENT edges — who does what to whom — that the ladder still lacks.

Interpretation-bound like 04-tags/tags.py, so it copies that pass's shape exactly: one generation
pass per scene, two turns over one conversation —
      Turn 1  the committed reading, replayed as the assistant's reasoning turn (build_reason_prompt).
      Turn 2  the edge list over the SAME number_scene-tagged scene text.
The cited `[n]` are therefore the identical per-scene tag numbers 04-tags resolved against
(number_scene is deterministic), so Step 4 joins each `[n]` through 04-tags -> the registry node.
NEVER renumber.

Output line grammar:
      - [<subj>] <predicate> [<obj>] | frame: <literal|simile|prophecy|reported> | lines <a>-<b>
One uniform binary edge per line; both ends are cited tags. `predicate` is one of the 31 canonical
labels in measure.CLOSED_VOCAB (the single source of truth — imported, not forked) plus the residual
fallback `relates-to`. There is NO `says-that` meta-edge: a reported/prophecy/simile proposition is
emitted as its CONTENT edge with the matching frame; who asserted it is recovered downstream by
joining the line range to 06-speech.

v1 scope: binary person<->being edges only — both ends must be a tagged referent; intransitive/state
verbs and movement to a place are out of scope (this is also what keeps the check total). Unlike
tags.py, a scene may legitimately produce ZERO edges (no binary relation present) — an empty edge
list passes; generation is skipped only when the scene has 0 tags.

Chain-of-thought is ON by default (`--no-think` disables); same justification as tags.py (Ollama
routes thinking to its own channel, call_llm caps runaway). The per-scene structural check guards
STRUCTURE only (the four "all checkable": tags exist, predicate/frame in vocabulary, line range in
scene); whether an edge is the RIGHT relation is interpretation, shipped as generated (no
hand-proofreading).

Input:  02-markup/<canticle>/NN.txt, 03-reading/<canticle>/NN.txt, scene ranges (dante_corpus API).
Output: 07-relations/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of edge lines (the
        file is the checkpoint: a finished scene is skipped on resume; delete to regenerate).
"""
import argparse
import re
import sys

from dante_analyze import (
    RELATIONS_DIR, READING_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup,
    load_readings, number_scene, unbrace, call_llm, step_sep,
    build_reason_prompt, out_path, done_scene_ends, restore_blocks, render_scene_block,
    append_canto,
)

from measure import CLOSED_VOCAB   # single source of truth for the predicate vocabulary

OUT_DIR = RELATIONS_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # the stronger reader (judgment-heavy relations)

RELATES_TO = "relates-to"                     # residual fallback predicate
PREDICATES = set(CLOSED_VOCAB) | {RELATES_TO}
FRAMES = {"literal", "simile", "prophecy", "reported"}


# ---------- reply parsing & check ----------

# Edge line: "- [subj] predicate [obj] | frame: F | lines a-b" (predicate one token). The `-b` is
# optional: the model very often writes a single line number for a one-line relation (`lines 81`),
# which we accept as `81-81` rather than burning a retry round on this common, unambiguous case —
# _render normalizes it back to `a-b`, so the committed file is always the strict two-number form
# (checkpoint.RELATIONS_LINE_RE stays strict).
RELATION_RE = re.compile(
    r"^-\s*\[(\d+)\]\s+(\S+)\s+\[(\d+)\]\s*\|\s*frame:\s*(\w+)\s*\|\s*lines\s+(\d+)(?:-(\d+))?\s*$"
)
# An intended-but-malformed edge line: starts like an edge but fails the grammar.
EDGE_PREFIX_RE = re.compile(r"^-\s*\[")


def parse_relations(text):
    """Parse a reply into (edges, malformed). `edges` is a list of {subj, predicate, obj, frame,
    start, end} dicts in file order; `malformed` is the list of raw lines that LOOK like an edge
    (`- [`) but do not match the grammar. Malformed lines are surfaced (not silently dropped)
    because — unlike tags.py — there is no completeness backstop here (zero edges is valid), so a
    garbled edge would otherwise vanish and the check pass spuriously. A single-number line range
    (`lines 81`) is read as `81-81`."""
    edges, malformed = [], []
    for raw in text.splitlines():
        m = RELATION_RE.match(raw)
        if m:
            start = int(m.group(5))
            edges.append({
                "subj": int(m.group(1)), "predicate": m.group(2), "obj": int(m.group(3)),
                "frame": m.group(4), "start": start,
                "end": int(m.group(6)) if m.group(6) else start,
            })
        elif EDGE_PREFIX_RE.match(raw):
            malformed.append(raw.strip())
    return edges, malformed


def check_relations(edges, malformed, k, s, e):
    """Check a scene's edges (tags 1..k, line range s..e). Returns a list of problems (empty = OK,
    including the empty-edge-list case). The structural invariants: every cited tag
    exists, every predicate/frame is in the closed vocabulary, every line range is within the scene.
    Structure only — whether the edge is the right relation is interpretation, shipped as generated."""
    problems = []
    for line in malformed:
        problems.append(f"malformed edge line (does not match the grammar): {line}")
    for ed in edges:
        tag = f"[{ed['subj']}] {ed['predicate']} [{ed['obj']}]"
        for role, n in (("subject", ed["subj"]), ("object", ed["obj"])):
            if not 1 <= n <= k:
                problems.append(f"{tag}: {role} tag [{n}] is not in this scene (tags 1-{k})")
        if ed["subj"] == ed["obj"]:
            problems.append(f"{tag}: subject and object are the same tag [{ed['subj']}]")
        if ed["predicate"] not in PREDICATES:
            problems.append(f"{tag}: predicate '{ed['predicate']}' is not in the closed vocabulary")
        if ed["frame"] not in FRAMES:
            problems.append(f"{tag}: frame '{ed['frame']}' is not one of {sorted(FRAMES)}")
        if not s <= ed["start"] <= ed["end"] <= e:
            problems.append(f"{tag}: lines {ed['start']}-{ed['end']} are outside the scene {s}-{e}")
    return problems


# ---------- prompts ----------

def _predicate_menu():
    """The closed predicate menu, derived straight from CLOSED_VOCAB so every canonical predicate
    is always listed (no separate grouping table to drift out of sync). Each line is the canonical
    label the model must emit + a few measured surface synonyms as a usage hint."""
    lines = []
    for canon, syns in CLOSED_VOCAB.items():
        hint = ", ".join(sorted(syns)[:4])
        lines.append(f"  {canon}  — e.g. {hint}")
    return "\n".join(lines)


def build_relations_prompt(k, s, e):
    """Turn 2: emit the edge list over the tagged scene already in the conversation. The reading
    (replayed as the assistant turn) established what happens; this turn formalizes the binary
    relations between tagged figures as citable edges. Frame is decided STRUCTURALLY in the
    generation rule below (not a post-hoc verification step). Examples are schematic only — never an
    edge drawn from the scene under test (no answer leakage)."""
    return f"""Now list the RELATIONS in the scene above as edges between numbered tags.

Each edge is ONE line, in exactly this form:

    - [a] predicate [b] | frame: F | lines x-y

where `[a]` (the subject/doer) and `[b]` (the object/undergoer) are BOTH numbered tags from this
scene (1 to {k}), `predicate` is a single label from the closed list below, `F` is the frame, and
`x-y` are the source line numbers where this relation is expressed (within {s}-{e}, x ≤ y; for a
relation on a single line, write that line twice, e.g. `lines 81-81`).

SCOPE — emit an edge ONLY when BOTH participants are tagged figures in this scene:
- A relation between two tagged figures/beings (a person, a soul, a beast, God) → emit it.
- An action with NO tagged object — moving to a place, a state or feeling, an attribute, an
  intransitive verb (appears, becomes, weeps, remains) — is OUT OF SCOPE; skip it.
- Do NOT invent a participant that has no tag, and do NOT use a tag number outside 1-{k}.

PREDICATE — choose the closest label from this closed list:
{_predicate_menu()}
If a genuine binary relation between two tagged figures fits NONE of these, use `{RELATES_TO}` as a
last resort. Prefer a specific predicate over `{RELATES_TO}`.

FRAME — decide by HOW the relation is presented in the text:
- `literal`   — a directly narrated event (it happens in the scene).
- `reported`  — the relation is the CONTENT of something a character says or reports (not narrated
                directly). Emit the content relation itself, e.g. `- [2] strikes [3]` with frame
                reported — do NOT add a separate "says" edge; who said it is recovered separately.
- `prophecy`  — a future event that is foretold or predicted.
- `simile`    — the figurative side of a comparison ("as a wolf chases a lamb").

If the scene contains NO binary relation between two tagged figures, output NOTHING (an empty list
is a valid answer — do not force an edge). Output only edge lines, one per relation, and nothing
else.

Schematic examples of the FORM only (not from this scene):
    - [a] guides [b] | frame: literal | lines x-y
    - [a] defeats [b] | frame: prophecy | lines x-y"""


def build_retry_prompt(problems, k, s, e):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The edge list did not pass the check:
{issues}

Produce it again, fixing these problems. Each edge is one line

    - [a] predicate [b] | frame: F | lines x-y

with `[a]` and `[b]` both tags from 1 to {k}, `predicate` from the closed list (or `{RELATES_TO}`),
`F` one of {sorted(FRAMES)}, and `x-y` within {s}-{e} (x ≤ y). Output only edge lines and nothing
else. If, after removing the flagged lines, no valid binary relation between two tagged figures
remains, output NOTHING — an empty list is a valid answer."""


# ---------- per-scene driver ----------

def relations_scene(canto, canto_title, s, e, scene_name, tagged, k, reading,
                    model, include_thoughts, max_attempts):
    """Produce one scene's edge list with `model`, gated by the structural check. Two turns over one
    conversation: the committed reading replayed as the reasoning turn, then the edge list over the
    same tagged scene. Returns the rendered edge text (possibly empty), keeping the last draft even
    if unresolved (flagged by caller)."""
    if k == 0:
        # No tagged figures: no binary edge is possible, so the edge list is empty by construction
        # (check_relations passes on []). Skip generation — asking for edges over tags [1]..[0]
        # only risks call_llm's empty/runaway guard, exactly as tags.py skips k==0.
        print(f"relations scene {s}-{e}: no tags, skipping generation", file=sys.stderr)
        return ""

    reason = build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, "", "")
    messages = [{"role": "user", "content": reason},
                {"role": "assistant", "content": reading},
                {"role": "user", "content": build_relations_prompt(k, s, e)}]

    step_sep("relations")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    draft = unbrace(resp.text)
    return _resolve(s, e, k, draft, messages, model, include_thoughts, max_attempts)


def _render(edges):
    """The canonical edge lines for parsed edges, in file order (well-formed lines only, so the
    committed file never carries malformed drafts)."""
    return "\n".join(
        f"- [{ed['subj']}] {ed['predicate']} [{ed['obj']}] | frame: {ed['frame']} "
        f"| lines {ed['start']}-{ed['end']}"
        for ed in edges
    )


def _resolve(s, e, k, draft, messages, model, include_thoughts, max_attempts):
    """Check `draft`, retrying in-conversation until it passes or `max_attempts` is hit; the last
    draft is kept (flagged, malformed lines dropped) if it never does. On success the edges are
    re-rendered to canonical form."""
    for attempt in range(1, max_attempts + 1):
        edges, malformed = parse_relations(draft)
        problems = check_relations(edges, malformed, k, s, e)
        if not problems:
            print(f"relations scene {s}-{e}: OK — {len(edges)} edge(s)", file=sys.stderr)
            return _render(edges)
        print(f"relations scene {s}-{e}: attempt {attempt}/{max_attempts}: "
              f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": build_retry_prompt(problems, k, s, e)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        draft = unbrace(resp.text)
    print(f"relations scene {s}-{e}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping last draft (flagged)", file=sys.stderr)
    return _render(parse_relations(draft)[0])


# ---------- canto driver ----------

def relations_canto(canticle, canto, gen_model, include_thoughts, max_attempts=3):
    """Build one canto's edges, scene by scene, each scene replaying its committed reading. The
    output file (NN.txt) is the checkpoint: each finished scene is written as it completes and
    skipped on resume (a zero-edge scene writes an empty body; its header still marks it done)."""
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
        tagged, k, _tagmeta = number_scene(lines, s, e)
        edges = relations_scene(canto, canto_title, s, e, scene_name, tagged, k, reading,
                                gen_model, include_thoughts, max_attempts)
        blocks.append(render_scene_block(s, e, scene_name, edges))
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
        relations_canto(canticle, canto, gen_model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Relations pass for Dante's Divina Commedia: per-scene subject-predicate-object "
                    "edges over the 04-tags numbering, bound to the committed reading.")
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
