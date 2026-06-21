"""
Presence pass for Dante's Divina Commedia (context-lock Step 3): per-scene PRESENT CAST vs
MERELY-MENTIONED referents. The action-only KG (08-kg) records who-does-what but does NOT mark who
is bodily PRESENT in a scene versus who is only NAMED (in speech, prophecy, simile, recollection).
The lock must preserve exactly that distinction; this pass supplies it, the person analogue of the
current-setting vs referred-to-place split 09-location/10-topography made for places.

A CLOSED-SET classification, not free extraction. The scene's figures are already resolved
upstream, so code gathers the roster — every figure the scene's 04-tags mentions, canonicalized
through 05-registry (raw_to_canonical), filtered to person-like node types (individual / generic /
class; set nodes expanded to members; non-person, hypothetical-simile, and deictic dropped — similes
are a separate code-join in the lock). The LLM only LABELS each roster figure `present` or `mentioned`.
This gives a strong structural check (every roster figure labeled exactly once, no figure outside
the roster) and reuses resolved identities instead of re-extracting them.

NO EXTERNAL CANON (repository premise). The roster comes from this repo's own derived pipeline
(04-tags / 05-registry), never external canon — exactly as 10 reads 09 and 08 reads 05/07.

Output line grammar (one per roster figure):
      - who: <canonical name> | status: present|mentioned | basis: <s>[-<e>]
`who` is the canonical node label (source spelling, matching the KG nodes); `status` is `present`
(bodily in the scene — acting, listening, addressed, or otherwise on stage) or `mentioned` (named
but not present); `basis` the source line number(s) within the scene that support the call. The
full quote is recoverable from the line refs at lock-assembly time (14-lock), so the checkable core
is a line reference, not a fragile string. A scene that names no person figure writes a `#` marker.

Chain-of-thought is ON by default (`--no-think` disables); same justification as location.py (the
present/mentioned reasoning runs in Ollama's own thinking channel, `resp.text` is the label lines,
call_llm caps runaway). The per-scene structural check guards STRUCTURE only — whether a figure is
REALLY present is interpretation, shipped as generated (no hand-proofreading). A soft present-anchor
check warns when a scene speaker (06-speech) or literal-frame action subject (08-kg) — present by
definition — is labeled `mentioned`; it is a warning, not fatal, because reported/prophecy frame
subjects can be absent.

Input:  02-markup/<canticle>/NN.txt (source lines), scene ranges (01-scenes JSON via load_scenes),
        04-tags + 05-registry (the roster), 06-speech + 08-kg (soft present-anchors).
Output: 11-presence/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of presence lines
        (the file is the checkpoint: a finished scene is skipped on resume; delete to regenerate).
"""
import argparse
import re
import sys

from dante_analyze import (
    PRESENCE_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup, strip_to_source,
    call_llm, step_sep, out_path, done_scene_ends, restore_blocks,
    render_scene_block, append_canto,
    load_tags, load_registry, load_speech, load_kg, raw_to_canonical, norm_label, fold_key,
)

OUT_DIR = PRESENCE_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # the stronger reader (judgment-heavy presence call)

# Registry node types that name a person-like figure (candidate cast). non-person (la Fortuna),
# hypothetical-simile (the swimmer, the miser), and deictic (scene-local "quel cane", a different
# figure each scene) are NOT cast; set nodes are expanded to members.
PERSON_TYPES = {"individual", "generic", "class"}
NO_CAST_MARKER = "# (no person figure named in this scene)"


# ---------- roster (code) ----------

def _canonical(label, raw2canon):
    """The registry canonical for a 04-tags label, or None if it does not resolve (`(unknown)` /
    an un-registered surface) — the same join 08-kg uses (fold_key(norm_label(...)))."""
    return raw2canon.get(fold_key(norm_label(label)))


def scene_roster(scene_tags, raw2canon, registry):
    """The closed set of person-like figures a scene mentions, as canonical labels in first-mention
    order. Each 04-tags label is canonicalized; a set node is expanded to its members; only
    person-like types are kept. Returns (roster, unresolved) where `roster` is the deduped ordered
    list and `unresolved` counts labels that did not resolve to a person node (tallied, not fatal)."""
    roster, seen, unresolved = [], set(), 0

    def add(canonical):
        node = registry.get(canonical)
        if node is None:
            return False
        if node["type"] == "set":
            hit = False
            for member in node["members"]:
                hit = add(member) or hit
            return hit
        if node["type"] in PERSON_TYPES:
            if canonical not in seen:
                seen.add(canonical)
                roster.append(canonical)
            return True
        return False  # non-person / hypothetical-simile

    for label in scene_tags.values():
        canonical = _canonical(label, raw2canon)
        if canonical is None or not add(canonical):
            if canonical is None:
                unresolved += 1
    return roster, unresolved


# ---------- reply parsing & check ----------

# A presence line: "- who: <name> | status: present|mentioned | basis: s[-e]".
PRESENCE_RE = re.compile(
    r"^-\s*who:\s*(?P<who>.*?)\s*\|\s*status:\s*(?P<status>\w+)\s*\|\s*"
    r"basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)
# An intended-but-malformed presence line: starts like one (`- `) but fails the grammar.
PRES_PREFIX_RE = re.compile(r"^-\s+\S")
VALID_STATUS = {"present", "mentioned"}


def parse_presence(text):
    """Parse a reply into (figs, malformed). `figs` is a list of {who, status, start, end} dicts in
    file order; `malformed` is the list of raw lines that LOOK like a presence line (`- …`) but do
    not match the grammar — surfaced (not dropped) so a garbled line cannot pass the check."""
    figs, malformed = [], []
    for raw in text.splitlines():
        m = PRESENCE_RE.match(raw)
        if m:
            start = int(m.group("bs"))
            figs.append({
                "who": m.group("who").strip(),
                "status": m.group("status").strip(),
                "start": start,
                "end": int(m.group("be")) if m.group("be") else start,
            })
        elif PRES_PREFIX_RE.match(raw):
            malformed.append(raw.strip())
    return figs, malformed


def check_presence(figs, malformed, roster, s, e):
    """Check a scene's presence list against the closed roster (line range s..e). Returns a list of
    problems (empty = OK). Structure only — whether a figure is REALLY present is interpretation,
    shipped as generated. Figures match the roster by fold_key, so a cosmetic spelling drift in the
    reply is tolerated and rendered back to the canonical roster label."""
    problems = []
    for line in malformed:
        problems.append(f"malformed presence line (does not match the grammar): {line}")

    roster_by_fold = {fold_key(name): name for name in roster}
    seen = {}
    for fig in figs:
        tag = f"who: {fig['who']!r}"
        if fig["status"] not in VALID_STATUS:
            problems.append(f"{tag}: status must be present|mentioned, got {fig['status']!r}")
        key = fold_key(fig["who"])
        if key not in roster_by_fold:
            problems.append(f"{tag}: not in the roster {roster} (classify only the listed figures)")
            continue
        seen.setdefault(key, 0)
        seen[key] += 1
        if seen[key] == 2:
            problems.append(f"{tag}: labeled more than once (give each roster figure exactly once)")
        if not s <= fig["start"] <= fig["end"] <= e:
            problems.append(f"{tag}: basis {fig['start']}-{fig['end']} is outside the scene {s}-{e}")

    for name in roster:
        if fold_key(name) not in seen:
            problems.append(f"who: {name!r}: roster figure not labeled (label every listed figure)")
    return problems


# ---------- prompts ----------

def _numbered_source(lines, s, e):
    """The scene's plain source, each line prefixed with its source line number, so the model can
    cite a correct `basis` and the checker can validate it."""
    return "\n".join(f"{ln} {strip_to_source(lines[ln - 1])}" for ln in range(s, e + 1))


def _roster_block(roster):
    return "\n".join(f"- {name}" for name in roster)


def build_presence_prompt(canto, canto_title, s, e, scene_name, source, roster):
    """The single generation turn: for each figure in the given roster, decide whether it is PRESENT
    in this scene or only MENTIONED. The roster is the closed set of figures already resolved for
    this scene; the model classifies it, it does not invent or drop members. Examples are schematic
    only — never a figure drawn from the scene under test (no answer leakage)."""
    return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

This is Canto {canto} — "{canto_title}". Here is scene "{scene_name}" (lines {s}-{e}), one source
line per number:

```
{source}
```

The following figures are referred to somewhere in this scene. For EACH of them, decide whether the
figure is PRESENT in the scene or only MENTIONED:

{roster}

Definitions:
- PRESENT — the figure is bodily on the scene during these lines: acting, moving, speaking, being
  spoken to, listening, or otherwise physically there.
- MENTIONED — the figure is only named or referred to: talked about, recalled, foretold, invoked,
  or used in a comparison, but is NOT physically present in these lines.

Rules:
- Judge from THESE LINES only. A figure can be the subject of talk yet absent (someone described, a
  soul far off, a person prophesied); that figure is MENTIONED, not PRESENT.
- Classify EVERY figure listed above, exactly once each, using the name AS GIVEN. Do not add a
  figure that is not listed, and do not drop one.

Output one line per figure, in exactly this form:

    - who: <name as listed> | status: present|mentioned | basis: x-y

where `status` is `present` or `mentioned`, and `x-y` are the source line number(s) within {s}-{e}
that justify the call (for a single line, write it once, e.g. `basis: {s}`).

Output only these lines, one per figure, and nothing else.

Schematic examples of the FORM only (not from this scene):
    - who: <a figure standing here> | status: present | basis: x-y
    - who: <a figure only talked about> | status: mentioned | basis: x-y"""


def build_retry_prompt(problems, roster, s, e):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The presence list did not pass the check:
{issues}

Produce it again, fixing these problems. Classify EACH listed figure exactly once:

{_roster_block(roster)}

Each line is

    - who: <name as listed> | status: present|mentioned | basis: x-y

with `status` either present or mentioned, and `x-y` within {s}-{e} (x ≤ y). Use the names exactly
as listed; do not add or drop a figure. Output only these lines and nothing else."""


# ---------- per-scene driver ----------

def _render(figs, roster):
    """The canonical presence lines for parsed figs, in roster order (well-formed, roster-matched
    lines only, rendered back to the canonical roster label so the committed file never carries a
    spelling drift or a malformed draft)."""
    roster_by_fold = {fold_key(name): name for name in roster}
    by_fold = {}
    for fig in figs:
        key = fold_key(fig["who"])
        if key in roster_by_fold and key not in by_fold:
            by_fold[key] = fig
    out = []
    for name in roster:
        fig = by_fold.get(fold_key(name))
        if fig:
            out.append(f"- who: {name} | status: {fig['status']} | "
                       f"basis: {fig['start']}-{fig['end']}")
    return "\n".join(out)


def presence_scene(canto, canto_title, s, e, scene_name, source, roster,
                   model, include_thoughts, max_attempts):
    """Classify one scene's roster with `model`, gated by the structural check. A single generation
    turn (the present/mentioned reasoning runs in the thinking channel), retried in-conversation
    until it passes or `max_attempts` is hit; the last draft is kept (flagged) if it never does."""
    messages = [{"role": "user",
                 "content": build_presence_prompt(canto, canto_title, s, e, scene_name,
                                                  source, _roster_block(roster))}]
    step_sep("presence")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    draft = resp.text
    for attempt in range(1, max_attempts + 1):
        figs, malformed = parse_presence(draft)
        problems = check_presence(figs, malformed, roster, s, e)
        if not problems:
            present = sum(1 for f in figs if f["status"] == "present")
            print(f"presence scene {s}-{e}: OK — {len(roster)} figure(s), {present} present",
                  file=sys.stderr)
            return _render(figs, roster)
        print(f"presence scene {s}-{e}: attempt {attempt}/{max_attempts}: "
              f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": build_retry_prompt(problems, roster, s, e)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        draft = resp.text
    print(f"presence scene {s}-{e}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping last draft (flagged)", file=sys.stderr)
    return _render(parse_presence(draft)[0], roster)


# ---------- present-anchors (soft check) ----------

def scene_anchors(canticle, canto, s, e, raw2canon, edges):
    """The set of canonical figures that are PRESENT BY DEFINITION in scene s..e: speakers of any
    06-speech span within the scene, and subjects of any 08-kg LITERAL-frame action edge in the
    scene. Used only for a soft warning (reported/prophecy subjects can be absent, so this is not
    fatal)."""
    anchors = set()
    for sp in load_speech(canticle, canto):
        if s <= sp["start"] and sp["end"] <= e:
            node = raw2canon.get(fold_key(norm_label(sp["speaker"])))
            if node:
                anchors.add(node)
    for edge in edges:
        if (edge["canto"] == canto and edge["scene"] == [s, e]
                and edge["frame"] == "literal" and edge["subj"]["node"]):
            anchors.add(edge["subj"]["node"])
    return anchors


# ---------- canto driver ----------

def presence_canto(canticle, canto, gen_model, include_thoughts,
                   registry, raw2canon, edges, max_attempts=3):
    """Build one canto's presence list, scene by scene. The output file (NN.txt) is the checkpoint:
    each finished scene is written as it completes and skipped on resume."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    tags = load_tags(canticle, canto)
    path = out_path(OUT_DIR, canticle, canto)

    done = done_scene_ends(path)
    blocks = restore_blocks(path)

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        roster, unresolved = scene_roster(tags.get((s, e), {}), raw2canon, registry)
        if unresolved:
            print(f"  note: {unresolved} tag label(s) did not resolve to a person node "
                  f"(skipped from the roster)", file=sys.stderr)
        if not roster:
            print(f"presence scene {s}-{e}: no person figure named — empty cast", file=sys.stderr)
            body = NO_CAST_MARKER
        else:
            source = _numbered_source(lines, s, e)
            body = presence_scene(canto, canto_title, s, e, scene_name, source, roster,
                                  gen_model, include_thoughts, max_attempts)
            # soft present-anchor check: a speaker / literal-frame subject is present by definition
            anchors = scene_anchors(canticle, canto, s, e, raw2canon, edges)
            figs, _ = parse_presence(body)
            mentioned = {f["who"] for f in figs if f["status"] == "mentioned"}
            for name in roster:
                if name in anchors and name in mentioned:
                    print(f"  note: {name!r} is a speaker / literal-frame subject in this scene "
                          f"(present by definition) but labeled `mentioned`", file=sys.stderr)
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

    registry = load_registry(canticle)
    raw2canon = raw_to_canonical(canticle)
    edges = load_kg(canticle)["edges"]   # for the soft literal-frame present-anchor

    for canto in targets:
        path = out_path(OUT_DIR, canticle, canto)
        if path.exists():
            _, scenes = load_scenes(canticle, canto)
            if done_scene_ends(path) >= {e for _, e, _ in scenes}:
                print(f"Canto {canto}: already complete at {path}, skipping.")
                continue
        presence_canto(canticle, canto, gen_model, include_thoughts, registry, raw2canon, edges)


def main():
    parser = argparse.ArgumentParser(
        description="Presence pass for Dante's Divina Commedia: per-scene present cast vs "
                    "merely-mentioned referents, classifying the resolved roster (04-tags / "
                    "05-registry).")
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
