"""
Cohort pass for Dante's Divina Commedia (context-lock Step 5): the COHORT of each scene — the class
of souls that DWELLS in / is punished in this place (the lustful, the gluttons, the heretics, the
blessed of a sphere …). The action-only KG (08-kg) records who does what but never this narrative
STATE; 10-topography fixes WHERE each scene is set, and this pass fixes WHO resides there. The lock's
`cohort` field is per scene, so the judgment is per scene; rollup.py later folds it onto the
canonical regions (10-topography), the place analogue of 05-registry's canonical view.

CODE-FIRST, LLM only for the residual (the 11-presence / 12-addressee method). The candidate cohorts
of a scene are the figures already resolved as PRESENT (11-presence, `status: present`) whose
05-registry type is `class` or `generic` — a collective of souls, not a named individual — minus a
small set of 2nd-person reader-apostrophes (`lettor`, …) which address the reader, never a resident
class. That closed set already lives upstream:

- 0 candidates  -> no soul-class present (a `#` marker); the scene contributes no cohort.
- 1 candidate   -> that class, source `code`. Deterministic, no LLM.
- >=2 candidates -> the LLM names which of the listed classes RESIDE here, source `llm`. Usually one;
  more than one is allowed (e.g. a guardian class and the punished souls are both present, or two
  soul-classes genuinely share a scene). Guardians/wardens, passers-by, and the travellers are
  excluded by the model — the residual it is the oracle for.

NO EXTERNAL CANON (repository premise). The candidate pool comes from this repo's own derived
pipeline (11-presence cast, 05-registry types), never an external list of the circles/terraces.

Output line grammar (one per cohort a scene resolves to, grouped under the scene):
      - cohort: <name> | source: code|llm|none | basis: <bs>[-<be>]
`cohort` is a canonical class/generic node label (source spelling, matching the registry); `source`
records how it was decided; `basis` the source line range supporting it (the present figure's basis
for the code path, the LLM-cited line for the residual). A scene with no present soul-class writes a
`#` marker.

Chain-of-thought is ON by default (`--no-think` disables); same justification as 11/12 (cohort is a
reading judgment and the output is a checked closed set, so call_llm caps runaway). The structural
check guards STRUCTURE only (each named cohort is in the candidate set, the basis is within the
scene); whether the reading is RIGHT is interpretation, shipped as generated (no hand-proofreading).

Input:  02-markup/<canticle>/NN.txt (source lines), scene ranges (01-scenes JSON via load_scenes),
        11-presence (present cast), 05-registry (figure types = the candidate filter).
Output: 13-cohort/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of cohort lines
        (the file is the checkpoint: a finished scene is skipped on resume; delete to regenerate).
"""
import argparse
import re
import sys

from dante_analyze import (
    COHORT_DIR, MAX_LENGTH, available_cantos, load_scenes, read_markup, strip_to_source,
    call_llm, step_sep, out_path, done_scene_ends, restore_blocks,
    render_scene_block, append_canto,
    load_presence, load_registry, fold_key,
)

OUT_DIR = COHORT_DIR
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"   # the stronger reader (cohort is reading-bound)

COHORT_TYPES = ("class", "generic")          # registry types that can name a body of souls
NO_COHORT_MARKER = "# (no soul-class present in this scene)"

# 2nd-person reader-apostrophes: typed class/generic but addressing the reader, never a resident
# soul-class. A conservative, mechanical drop (the bare vocative only); phrase apostrophes
# ("tu che leggi", "voialtri pochi") are left for the model, which excludes non-residents anyway.
READER_FORMS = {fold_key(w) for w in ("lettor", "lettore", "lettori")}


# ---------- candidate pool (code) ----------

def scene_candidates(presence_figs, registry):
    """The closed cohort candidates of a scene: present figures whose registry type is class/generic
    (a collective of souls), reader-apostrophes dropped, deduped by fold_key in first-appearance
    order. Each candidate keeps the present figure's basis (used for the code path)."""
    cands, seen = [], set()
    for fig in presence_figs:
        if fig["status"] != "present":
            continue
        who = fig["who"]
        node = registry.get(who)
        if node is None or node["type"] not in COHORT_TYPES:
            continue
        key = fold_key(who)
        if key in READER_FORMS or key in seen:
            continue
        seen.add(key)
        cands.append({"who": who, "basis_start": fig["basis_start"], "basis_end": fig["basis_end"]})
    return cands


# ---------- LLM reply parsing & check ----------

# A cohort reply line: "cohort: <name> | basis: x[-y]" (leading "- " tolerated). One or more.
COHORT_REPLY_RE = re.compile(
    r"^-?\s*cohort:\s*(?P<name>.*?)\s*\|\s*basis:\s*(?P<bs>\d+)(?:-(?P<be>\d+))?\s*$"
)
COHORT_PREFIX_RE = re.compile(r"^-?\s*cohort:")


def parse_cohort(text):
    """Parse a reply into (picks, malformed). `picks` is the list of well-formed {name, start, end}
    dicts in reply order; `malformed` is raw lines that LOOK like a cohort line but fail the grammar
    (surfaced, not dropped, so a garbled line cannot pass the check)."""
    picks, malformed = [], []
    for raw in text.splitlines():
        m = COHORT_REPLY_RE.match(raw)
        if m:
            start = int(m.group("bs"))
            picks.append({
                "name": m.group("name").strip(),
                "start": start,
                "end": int(m.group("be")) if m.group("be") else start,
            })
        elif COHORT_PREFIX_RE.match(raw):
            malformed.append(raw.strip())
    return picks, malformed


def check_cohort(picks, malformed, candidates, s, e):
    """Check parsed cohorts against the closed candidate set (scene lines s..e). Returns a list of
    problems (empty = OK). Structure only — whether the reading is RIGHT is interpretation. Each
    pick matches a candidate by fold_key, so a cosmetic spelling drift is tolerated and rendered
    back to the canonical label."""
    problems = []
    for line in malformed:
        problems.append(f"malformed cohort line (does not match the grammar): {line}")
    if not picks:
        problems.append("no cohort line produced (give at least one)")
        return problems
    cand_by_fold = {fold_key(c["who"]): c["who"] for c in candidates}
    chosen = set()
    for p in picks:
        key = fold_key(p["name"])
        if key not in cand_by_fold:
            problems.append(f"cohort {p['name']!r}: not in the candidate list "
                            f"{[c['who'] for c in candidates]} (choose from the listed classes only)")
        elif key in chosen:
            problems.append(f"cohort {p['name']!r}: listed more than once (give each class at most once)")
        else:
            chosen.add(key)
        if not s <= p["start"] <= p["end"] <= e:
            problems.append(f"basis {p['start']}-{p['end']} is outside the scene {s}-{e}")
    return problems


# ---------- prompts ----------

def _numbered_source(lines, s, e):
    """The scene's plain source, each line prefixed with its source line number, so the model can
    cite a correct `basis` and the checker can validate it."""
    return "\n".join(f"{ln} {strip_to_source(lines[ln - 1])}" for ln in range(s, e + 1))


def _candidate_block(candidates):
    return "\n".join(f"- {c['who']}" for c in candidates)


def build_cohort_prompt(canto, canto_title, s, e, scene_name, source, candidates):
    """The single generation turn: from the listed collective figures (already resolved as PRESENT in
    this scene), name which one(s) are the COHORT — the class of souls that dwells in / is punished
    in this place. The model picks from the list; it does not invent or add a figure. Examples are
    schematic only — never a figure drawn from the scene under test (no answer leakage)."""
    return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

This is Canto {canto} — "{canto_title}". Here is scene "{scene_name}" (lines {s}-{e}), one source
line per number:

```
{source}
```

The following collective figures are PRESENT in this scene. Decide which of them are the COHORT —
the class of souls that DWELLS in this place / is punished or rewarded here (its resident
inhabitants):

{_candidate_block(candidates)}

Rules:
- The cohort is the body of souls whose place this is. EXCLUDE guardians or wardens set over them
  (e.g. demons, monsters, angels on duty), figures merely passing through, and the travellers
  themselves — name only the souls who belong here.
- Choose from the list above, using each name AS GIVEN. Do not add a figure that is not listed.
- Usually ONE class is the cohort. Give more than one only if two listed classes both genuinely
  reside here.

Output one line per chosen cohort, in this form:

    cohort: <name as listed> | basis: x-y

where `x-y` are the source line number(s) within {s}-{e} that justify it (for a single line, write
it once, e.g. `basis: {s}`).

Output only those line(s) and nothing else.

Schematic example of the FORM only (not from this scene):
    cohort: <the class of souls whose place this is> | basis: x-y"""


def build_retry_prompt(problems, candidates, s, e):
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The cohort did not pass the check:
{issues}

Choose again which listed class(es) are the souls whose place this is, from this list only:

{_candidate_block(candidates)}

Output one line per chosen cohort

    cohort: <name as listed> | basis: x-y

with `x-y` within {s}-{e} (x <= y). Use a name exactly as listed; do not add a figure; give each
class at most once. Output only those line(s) and nothing else."""


# ---------- per-scene driver ----------

def render_line(name, source, bs, be):
    return f"- cohort: {name} | source: {source} | basis: {bs}-{be}"


def cohort_scene_llm(canto, canto_title, s, e, scene_name, source, candidates,
                     model, include_thoughts, max_attempts):
    """Resolve one ambiguous scene (>=2 candidates) with `model`, gated by the structural check. A
    single generation turn (the reasoning runs in the thinking channel), retried in-conversation
    until it passes or `max_attempts` is hit; the last draft is kept (flagged) if it never does.
    Returns a list of (name, bs, be)."""
    messages = [{"role": "user",
                 "content": build_cohort_prompt(canto, canto_title, s, e, scene_name, source,
                                                candidates)}]
    step_sep("cohort")
    resp = call_llm(messages, model, include_thoughts=include_thoughts)
    draft = resp.text
    cand_by_fold = {fold_key(c["who"]): c["who"] for c in candidates}
    for attempt in range(1, max_attempts + 1):
        picks, malformed = parse_cohort(draft)
        problems = check_cohort(picks, malformed, candidates, s, e)
        if not problems:
            out = [(cand_by_fold[fold_key(p["name"])], p["start"], p["end"]) for p in picks]
            names = ", ".join(n for n, _, _ in out)
            print(f"cohort {s}-{e}: OK — {names}", file=sys.stderr)
            return out
        print(f"cohort {s}-{e}: attempt {attempt}/{max_attempts}: {len(problems)} problem(s):",
              file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": build_retry_prompt(problems, candidates, s, e)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=include_thoughts)
        draft = resp.text
    # keep whatever valid picks the last draft named; fall back to the first candidate if none.
    picks, _ = parse_cohort(draft)
    out, chosen = [], set()
    for p in picks:
        key = fold_key(p["name"])
        if key in cand_by_fold and key not in chosen and s <= p["start"] <= p["end"] <= e:
            chosen.add(key)
            out.append((cand_by_fold[key], p["start"], p["end"]))
    if not out:
        c = candidates[0]
        out = [(c["who"], c["basis_start"], c["basis_end"])]
    print(f"cohort {s}-{e}: NOT resolved after {max_attempts} attempt(s); "
          f"keeping {[n for n, _, _ in out]} (flagged)", file=sys.stderr)
    return out


def resolve_scene(canto, canto_title, s, e, scene_name, lines, candidates,
                  model, include_thoughts, max_attempts):
    """The cohort line(s) for one scene: code where the candidate pool is 0 or 1, the LLM only for
    >=2 (the residual method)."""
    if not candidates:
        return NO_COHORT_MARKER
    if len(candidates) == 1:
        c = candidates[0]
        return render_line(c["who"], "code", c["basis_start"], c["basis_end"])
    source = _numbered_source(lines, s, e)
    picks = cohort_scene_llm(canto, canto_title, s, e, scene_name, source, candidates,
                             model, include_thoughts, max_attempts)
    return "\n".join(render_line(name, "llm", bs, be) for name, bs, be in picks)


# ---------- canto driver ----------

def cohort_canto(canticle, canto, gen_model, include_thoughts, max_attempts=3):
    """Build one canto's cohort list, scene by scene. The output file (NN.txt) is the checkpoint:
    each finished scene is written as it completes and skipped on resume."""
    lines = read_markup(canticle, canto)
    canto_title, scenes = load_scenes(canticle, canto)
    presence = load_presence(canticle, canto)
    registry = load_registry(canticle)
    path = out_path(OUT_DIR, canticle, canto)

    done = done_scene_ends(path)
    blocks = restore_blocks(path)

    print(f"Canto {canto}: {len(lines)} lines, {len(scenes)} scenes.")
    for s, e, scene_name in scenes:
        if e in done:
            print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} [skipped] =====")
            continue
        print(f"\n===== Canto {canto}, scene {s}-{e}: {scene_name} =====")
        candidates = scene_candidates(presence.get((s, e), []), registry)
        body = resolve_scene(canto, canto_title, s, e, scene_name, lines, candidates,
                             gen_model, include_thoughts, max_attempts)
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
        cohort_canto(canticle, canto, gen_model, include_thoughts)


def main():
    parser = argparse.ArgumentParser(
        description="Cohort pass for Dante's Divina Commedia: the class of souls that dwells in each "
                    "scene, code for 0/1 present soul-classes, LLM only when several are present "
                    "(candidate pool = 11-presence present cast filtered to 05-registry class/generic).")
    parser.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"LLM for the residual cohort judgment (default: {DEFAULT_MODEL})")
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
