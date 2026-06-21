#!/usr/bin/env python
"""
Coreference overlay — Step 2 of identity resolution (the residual Fix 1 could not do).

Fix 1 (`aliases.txt`) merges spelling variants GLOBALLY — safe only when one surface always means
one figure. The residual is the opposite case: an UNDER-SPECIFIED label (bare `Guido`, `Latino`,
`Pietro`) that means DIFFERENT figures in different scenes, so no global alias is correct. This pass
decides, per SCENE and with the scene's context, which fuller-form figure (if any) an under-specified
label refers to, and writes a per-tag correction to `04-tags/coref.txt`.

Why per-tag at the tag layer, not in the registry: the downstream join `raw_to_canonical` is a
global `fold_key -> canonical` map and CANNOT route one surface to two nodes. The disambiguation has
to live in the label itself, applied where every consumer reads it (`load_tags`). Once a tag's label
is identity-first, the existing fold_key join folds it onto the right node automatically — no change
to 06/08/11.

This is the ONLY step here that calls the model, and it CANNOT be structurally verified (a wrong
merge passes every check). So its output is staged in `04-tags/coref.txt` for human review before
commit, and every decision (including "distinct") is recorded in `coref.cache.txt` for resume and
audit. Run it, READ the proposals, delete the wrong ones, then rebuild the registry.

Granularity: one decision per (label, canticle, canto, scene), applied to every occurrence of that
label in the scene — 04-tags already aims for intra-scene label consistency, so a scene's `Guido` is
one figure. There are TWO candidate kinds:

- **Bare name -> fuller form (lexical).** The candidate targets for a single-token bare label are the
  fuller individual nodes it HEADS as a proper name (`Guido` -> `Guido da Montefeltro`, …; `Latino` ->
  `Brunetto Latino`) — see heads_name, which excludes governed periphrases (`l'ombra di Dante`,
  `Figliuol di Dio`) where the bare name is not the head — plus a small seed map for semantic pairs no
  token test catches (`Iesù` -> `Cristo`). Superclass terms whose fuller forms name distinct figures
  are excluded outright (EXCLUDE_BARE: `Dio`, which spans the three Trinity persons).
- **Epithet -> co-present named figure (scene-local).** A genuine epithet/periphrasis
  (`il Navarrese`, `la madre`, `l'angelo`: `individual`-typed, not a proper name, not `deictic`)
  shares NO name token with its referent, so it has no lexical candidate. Its candidates are the NAMED
  individuals co-present in that same scene, recomputed per scene (see `epithet_labels`,
  `gather_epithet_scenes`). The poem frequently leaves such a figure unnamed, so `distinct` (no merge)
  is the common, correct answer; this is the deferred part-B grouping (see root `KG-PROBLEM.md`), an
  unverifiable merge that the human review of `coref.txt` is the safeguard for.

Run it as ONE process — do NOT parallelize per canticle (same hazard as registry.py). Both outputs
are GLOBAL single files with no locking: `coref.cache.txt` is append-on-decision (concurrent appends
corrupt it), and `coref.txt` is rewritten WHOLE from the in-memory cache at the end of the run, so a
second process clobbers the first's corrections (last-writer-wins). The intended invocation is the
single `coreference.py inferno purgatorio paradiso` that `make -C 04-tags coref` runs.

Layering: this generator lives in 04-tags because its output is a TAGS patch — it writes only into
04-tags, and `load_tags()` (the 04-tags reader) applies it. Its inputs are all upstream in the linear
chain `tags.py -> node_types.py -> coreference.py -> 05-registry/registry.py`: the typing info comes
from its sibling 04-tags/types.txt (produced by node_types.py), the deterministic alias table from
05-registry/aliases.txt (hand-maintained). Both are read as DATA via the shared loaders — no
cross-pass code import, no back-edge.

Input:  04-tags/<canticle>/NN.txt    (committed; the labels to correct)
        04-tags/types.txt            (typing cache; overlay-free type info = candidate targets,
                                      produced by node_types.py one step upstream)
        03-reading/<canticle>/NN.txt  (scene context for the judgment)
Output: 04-tags/coref.txt            (the overlay, human-reviewable)
        04-tags/coref.cache.txt      (resume + audit cache; every decision incl. "distinct")
"""
import argparse
import re
import sys

# The candidate targets come from 04-tags/types.txt (load_types_cache), the OVERLAY-FREE typing cache
# produced by node_types.py one step upstream — NOT the committed 05-registry/<canticle>.txt node
# set, which is built WITH this overlay applied. Reading the node set would make coref depend on its
# own downstream output (a build-time cycle); types.txt, built overlay-free before this step, keeps
# the dependency a linear DAG (tags -> node_types -> coref -> registry). aliases.txt (hand-maintained)
# is read the same way, as DATA, so there is no cross-pass code import.
from dante_analyze import (
    TAGS_DIR, MAX_LENGTH,
    read_markup, load_tags, load_readings, number_scene,
    norm_label, fold_key, is_capitalized_name, is_deictic, call_llm, step_sep,
    load_types_cache, load_aliases, ALIASES_FILE,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
DISTINCT = "distinct"
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"
COREF_FILE = TAGS_DIR / "coref.txt"
COREF_CACHE = TAGS_DIR / "coref.cache.txt"

# Semantic merge targets a token test cannot catch (bare label -> candidate canonicals).
SEED_TARGETS = {
    "Iesù": ["Cristo"],
}

COREF_HEADER = (
    "# Per-tag coreference overlay: canticle/canto/start-end/tag_no = identity-first label\n"
    "# Upgrades under-specified 04-tags labels (bare names, periphrases) to their identity-first\n"
    "# form, applied at load_tags() so every consumer sees the same per-tag identity.\n"
    "# Generated by 04-tags/coreference.py; human-reviewable before committing.\n"
)


def committed_cantos(canticle):
    """Cantos with a committed 04-tags file, in order."""
    d = TAGS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


# ---------- candidates ----------

# Function words that GOVERN a following noun: a bare name preceded by one of these is not the
# proper-name head of the form but the object/possessee of the governor, so the form is a periphrasis
# denoting a related entity, not a fuller name OF the figure. Prepositions ("X di Dio", "l'ombra di
# Dante"), possessives ("vicario suo Cristo"), and demonstratives ("l'altro Carlo") all qualify.
# Plain articles are NOT here: "la Pia" is a legitimate fuller name (article + proper name).
GOVERNORS = {
    "di", "del", "dello", "della", "dei", "degli", "delle",
    "da", "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "de", "de'", "d'", "a", "in", "con", "su", "per", "tra", "fra",
    "suo", "sua", "suoi", "sue", "mio", "mia", "miei", "mie",
    "tuo", "tua", "tuoi", "tue", "nostro", "nostra", "vostro", "vostra", "loro",
    "altro", "altra", "altri", "altre", "l'altro", "l'altra",
    "quel", "quello", "quella", "quei", "quegli", "quelle", "questo", "questa",
}

# Bare names that must NOT auto-merge into a fuller form: superclass/ambiguous terms whose fuller
# forms denote DISTINCT figures, so a per-scene merge over-commits. "Dio" spans the three Trinity
# persons ("Dio Padre / Dio Figlio / Dio Spirito Santo") and the bare word almost always means
# God-in-general — leave it distinct rather than fold it into one person.
EXCLUDE_BARE = {"Dio"}


def heads_name(bare, fuller):
    """True if single-token `bare` is the proper-name HEAD of multi-token `fuller`: it occurs as a
    token that is NOT preceded by a GOVERNOR. So "San Pietro", "conte Ugolino", "Tommaso d'Aquino"
    qualify (title/honorific or first-token), but governed periphrases "l'ombra di Dante",
    "Figliuol di Dio", "vicario suo Cristo", "l'altro Carlo" do not — there `bare` follows a
    preposition/possessive/demonstrative and the form names a related or contrasted entity."""
    toks = fuller.split()
    return any(t == bare and (i == 0 or toks[i - 1].lower() not in GOVERNORS)
               for i, t in enumerate(toks))


def candidate_targets(types):
    """{bare_label: [fuller canonical, …]} from `types` ({canonical: type}, i.e. load_types_cache) —
    under-specified individual labels paired with the fuller individual labels they could resolve to.
    A bare label is a single-token `individual`; a target is a multi-token `individual` that the bare
    label HEADS as a proper name (see heads_name — excludes governed periphrases like "X di Dio"),
    plus SEED_TARGETS. Type info is global and overlay-free, so candidates do not depend on whether
    the overlay has been applied."""
    individuals = [c for c, t in types.items() if t == "individual"]
    bare = [c for c in individuals if " " not in c and c not in EXCLUDE_BARE]
    out = {}
    for b in bare:
        targets = sorted(c for c in individuals if c != b and heads_name(b, c))
        for extra in SEED_TARGETS.get(b, []):
            if types.get(extra) and extra not in targets:
                targets.append(extra)
        if targets:
            out[b] = targets
    return out


def gather_occurrences(canticle, bare_labels):
    """{(label, canto, s, e): [tag_no, …]} for every scene where a candidate bare label occurs.
    Reads through load_tags, so a tag already corrected in the overlay no longer matches (skipped)."""
    occ = {}
    wanted = {norm_label(b): b for b in bare_labels}
    for canto in committed_cantos(canticle):
        for (s, e), res in load_tags(canticle, canto, apply_coref=False).items():
            for tag_no, raw in res.items():
                b = wanted.get(norm_label(raw))
                if b is not None:
                    occ.setdefault((b, canto, s, e), []).append(tag_no)
    return occ


# ---------- candidates: epithets / periphrases (the scene-local case) ----------

# The bare-name path above resolves an under-specified PROPER NAME to a fuller form bearing the same
# name token (heads_name) — a lexical, scene-independent candidate. A genuine epithet / periphrasis
# ("il Navarrese", "la madre", "l'angelo") shares NO name token with its referent, so its candidates
# cannot be lexical: they are the NAMED figures co-present in that same scene, recomputed per scene.
# The poem often leaves such a figure unnamed, so `distinct` is the common, safe answer; the merge is
# interpretation with no structural check, which is exactly why the overlay is human-reviewed.

def epithet_labels(types):
    """Genuine epithet/periphrasis canonicals (the part-B grouping target): `individual`-typed labels
    that are not proper names (`is_capitalized_name`) and not `deictic`. These name a figure the poem
    MAY identify elsewhere, but their merge candidates are scene-local (the co-present named figures),
    not lexical — so they are decided with a per-scene candidate list, disjoint from the bare-name
    path (a multi-token periphrasis is never in `candidate_targets`, whose `bare` keys are
    single-token; a single-token epithet like `figlio` heads no fuller name, so it has no lexical
    target there either)."""
    return [c for c, t in types.items()
            if t == "individual" and not is_capitalized_name(c) and not is_deictic(c)]


def named_individuals(types):
    """{fold_key: canonical} for every NAMED `individual` (the merge targets an epithet can resolve
    to). Keyed by `fold_key` — the same global join `raw_to_canonical` uses — so a co-present tag in
    any spelling folds onto its named node."""
    return {fold_key(c): c for c, t in types.items()
            if t == "individual" and is_capitalized_name(c)}


def gather_epithet_scenes(canticle, epi_labels, named_by_fold):
    """{(label, canto, s, e): [co-present named canonical, …]} for every scene where an epithet label
    occurs alongside >=1 named individual — the per-scene candidate list. Read with the overlay
    applied (apply_coref=True) so candidates reflect committed merges and an epithet already corrected
    by a prior run drops out (its tag now carries the named form). The epithet occurrence is matched
    by `norm_label` (so `write_overlay`, which expands the decision to tag numbers by the same key,
    always finds it); the co-present NAMED candidates are folded by `fold_key` (the global
    `raw_to_canonical` join) so a variant spelling resolves onto its named node."""
    wanted = {norm_label(b): b for b in epi_labels}
    out = {}
    for canto in committed_cantos(canticle):
        for (s, e), res in load_tags(canticle, canto, apply_coref=True).items():
            vals = list(res.values())
            present = sorted({named_by_fold[fold_key(v)] for v in vals
                              if fold_key(v) in named_by_fold})
            if not present:
                continue
            for v in set(vals):
                b = wanted.get(norm_label(v))
                if b is not None:
                    out[(b, canto, s, e)] = present
    return out


# ---------- resume cache ----------

CACHE_RE = re.compile(r"^\s*(\w+)/(\d+)/(\d+)-(\d+)\s+(.*\S)\s*=\s*(.*\S)\s*$")


def load_cache():
    """{(canticle, canto, s, e, label): decision} from coref.cache.txt (decision = a canonical or
    'distinct')."""
    out = {}
    if COREF_CACHE.exists():
        for line in COREF_CACHE.read_text(encoding="utf-8").splitlines():
            m = CACHE_RE.match(line)
            if m:
                canticle, canto, s, e = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
                out[(canticle, canto, s, e, m.group(5))] = m.group(6)
    return out


def append_cache(canticle, canto, s, e, label, decision):
    with COREF_CACHE.open("a", encoding="utf-8") as f:
        f.write(f"{canticle}/{canto}/{s}-{e} {label} = {decision}\n")


def write_overlay(cache, types):
    """Regenerate 04-tags/coref.txt from the cache: per-tag lines for every non-'distinct' decision.
    Re-reads each scene RAW (apply_coref=False) to expand a (label, scene) decision to the tag
    numbers that carry the bare label.

    A decision is dropped if it no longer passes its structural candidate test — bare names by
    `heads_name` / a SEED_TARGETS pair, epithets by `decision` still being a named individual in
    `types` (the part-B target must resolve to a real proper-name node) — so tightening candidate
    generation cleans the overlay on the next regenerate WITHOUT a model rerun. The test is on the
    label/target STRINGS and the upstream typing cache only, never re-derived from the registry: the
    committed registry already reflects the prior overlay (merged labels are gone from it), so
    re-deriving candidates there would wrongly drop the very corrections that worked."""
    named_by_fold = named_individuals(types)
    by_scene = {}   # (canticle, canto, s, e) -> {norm_label: decision}
    for (canticle, canto, s, e, label), decision in cache.items():
        if decision == DISTINCT or label in EXCLUDE_BARE:
            continue
        bare_ok = heads_name(label, decision) or decision in SEED_TARGETS.get(label, [])
        epi_ok = (not is_capitalized_name(label) and not is_deictic(label)
                  and fold_key(decision) in named_by_fold)
        if not (bare_ok or epi_ok):
            continue
        by_scene.setdefault((canticle, canto, s, e), {})[norm_label(label)] = decision
    lines = []
    for (canticle, canto, s, e) in sorted(by_scene):
        res = load_tags(canticle, canto, apply_coref=False).get((s, e), {})
        for tag_no in sorted(res):
            decision = by_scene[(canticle, canto, s, e)].get(norm_label(res[tag_no]))
            if decision:
                lines.append(f"{canticle}/{canto}/{s}-{e}/{tag_no} = {decision}")
    COREF_FILE.write_text(COREF_HEADER + "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


# ---------- LLM ----------

def build_prompt(label, targets, source_text, reading):
    """Ask which fuller figure (if any) `label` denotes in THIS scene. Source text + reading are
    scene context; the candidate list is general knowledge about who shares the name. No per-item
    answer is supplied — the model must read the scene."""
    listing = "\n".join(f"{i}. {t}" for i, t in enumerate(targets, 1))
    return f"""In one scene of Dante's Divine Comedy a figure is referred to by the under-specified
label "{label}". Several distinct figures in the poem share that name; decide which one — if any —
"{label}" refers to IN THIS SCENE, using the scene below.

Scene (source text):
{source_text}

Scene (reading):
{reading}

Candidates that "{label}" could be (figures elsewhere in the poem bearing this name):
{listing}
{len(targets) + 1}. {DISTINCT} — none of the above; "{label}" here is a different or unidentifiable figure.

Answer with exactly one line:

    {label} = <one candidate exactly as listed, or {DISTINCT}>

Echo "{label}" verbatim. Output only that one line and nothing else."""


def build_epithet_prompt(label, candidates, source_text, reading):
    """Ask which NAMED figure present in this scene the epithet/periphrasis `label` denotes, if any.
    Unlike the bare-name prompt, the candidates are the figures co-present in THIS scene (the epithet
    shares no name with its referent), and the poem often leaves the figure unnamed — so `distinct`
    is a frequent, correct answer. The scene is the only evidence; no per-item answer is supplied."""
    listing = "\n".join(f"{i}. {t}" for i, t in enumerate(candidates, 1))
    return f"""In one scene of Dante's Divine Comedy a figure is referred to by the epithet or
periphrasis "{label}" — a descriptive phrase, not a proper name. Decide which NAMED figure present in
THIS scene "{label}" denotes, if any, using the scene below. The poem frequently leaves such a figure
unnamed; if "{label}" is not one of the named figures present, answer {DISTINCT} — do NOT guess.

Scene (source text):
{source_text}

Scene (reading):
{reading}

Named figures present in this scene that "{label}" could denote:
{listing}
{len(candidates) + 1}. {DISTINCT} — "{label}" denotes none of the above (the figure is unnamed here, or not present).

Answer with exactly one line:

    {label} = <one candidate exactly as listed, or {DISTINCT}>

Echo "{label}" verbatim. Output only that one line and nothing else."""


ANSWER_RE = re.compile(r"^\s*(.*\S)\s*=\s*(.*\S)\s*$")


def parse_answer(text, label, targets):
    """The chosen decision (a target canonical or DISTINCT), or None if unparseable/invalid."""
    for raw in text.splitlines():
        m = ANSWER_RE.match(raw)
        if not m:
            continue
        if norm_label(m.group(1)) != norm_label(label):
            continue
        choice = m.group(2).strip()
        if choice == DISTINCT:
            return DISTINCT
        for t in targets:
            if norm_label(choice) == norm_label(t):
                return t
    return None


def decide(label, targets, prompt_text, model, max_attempts=3):
    """One scene decision, retried in-conversation until parseable, else DISTINCT (the safe default:
    no correction, leave the label as committed). `prompt_text` is the initial question (bare-name
    `build_prompt` or epithet `build_epithet_prompt`); `targets` is the candidate list parse_answer
    validates the answer against."""
    messages = [{"role": "user", "content": prompt_text}]
    step_sep("coreference")
    resp = call_llm(messages, model, include_thoughts=True)
    for attempt in range(1, max_attempts + 1):
        decision = parse_answer(resp.text, label, targets)
        if decision is not None:
            return decision
        if attempt >= max_attempts:
            break
        messages += [
            {"role": "assistant", "content": resp.text},
            {"role": "user", "content": f'Answer again with one line `{label} = <candidate or '
                                         f'{DISTINCT}>`, the candidate echoed exactly as listed.'},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=True)
    print(f"coref: {label}: unparseable after {max_attempts} attempts; defaulting to {DISTINCT}",
          file=sys.stderr)
    return DISTINCT


# ---------- driver ----------

def main():
    ap = argparse.ArgumentParser(
        description="Coreference overlay (KG identity Step 2): resolve under-specified labels "
                    "per scene (see 05-registry/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to process (default: all three)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"LLM for the coreference judgment (default: {DEFAULT_MODEL})")
    args = ap.parse_args()

    cache = load_cache()
    # types.txt is an append-only superset: drop canonicals that aliases.txt has since absorbed
    # (Fix 1), so coref does not offer alias pairs (e.g. "Cristo" -> "Iesù Cristo") as candidates.
    types = load_types_cache()
    for alias, _canonical in load_aliases(ALIASES_FILE):
        types.pop(alias, None)
    targets_of = candidate_targets(types)                # bare-name -> fuller, global/overlay-free
    # part-B epithets (scene-local candidates); drop any already owned by the bare-name path
    # (a single-token label that heads_name a fuller form, e.g. `rege`/`figlio`) so the two paths
    # are disjoint and never double-decide a (label, scene).
    epi_labels = [c for c in epithet_labels(types) if c not in targets_of]
    named_by_fold = named_individuals(types)
    for canticle in args.canticles:
        # --- bare-name path: under-specified proper name -> fuller form (lexical candidates) ---
        occ = gather_occurrences(canticle, list(targets_of))
        scenes = sorted(occ)
        print(f"coref {canticle}: {len(targets_of)} bare-name label(s), {len(scenes)} scene(s) to "
              f"decide", file=sys.stderr)
        for (label, canto, s, e) in scenes:
            ck = (canticle, canto, s, e, label)
            if ck in cache:
                continue
            markup = read_markup(canticle, canto)
            source_text, _k, _meta = number_scene(markup, s, e)
            reading = load_readings(canticle, canto).get((s, e), "")
            prompt = build_prompt(label, targets_of[label], source_text, reading)
            decision = decide(label, targets_of[label], prompt, args.model)
            append_cache(canticle, canto, s, e, label, decision)
            cache[ck] = decision
            mark = decision if decision != DISTINCT else "(distinct — no correction)"
            print(f"coref {canticle} {canto} {s}-{e}: {label} -> {mark}", file=sys.stderr)

        # --- epithet path: periphrasis -> a NAMED figure co-present in the scene (or distinct) ---
        epi_occ = gather_epithet_scenes(canticle, epi_labels, named_by_fold)
        print(f"coref {canticle}: {len(epi_labels)} epithet label(s), {len(epi_occ)} scene(s) with a "
              f"co-present named candidate", file=sys.stderr)
        for (label, canto, s, e) in sorted(epi_occ):
            ck = (canticle, canto, s, e, label)
            if ck in cache:
                continue
            candidates = epi_occ[(label, canto, s, e)]
            markup = read_markup(canticle, canto)
            source_text, _k, _meta = number_scene(markup, s, e)
            reading = load_readings(canticle, canto).get((s, e), "")
            prompt = build_epithet_prompt(label, candidates, source_text, reading)
            decision = decide(label, candidates, prompt, args.model)
            append_cache(canticle, canto, s, e, label, decision)
            cache[ck] = decision
            mark = decision if decision != DISTINCT else "(distinct — no correction)"
            print(f"coref {canticle} {canto} {s}-{e}: {label} -> {mark}", file=sys.stderr)

    write_overlay(cache, types)
    n = sum(1 for v in cache.values() if v != DISTINCT)
    print(f"coref: {n} correction(s) written to {COREF_FILE} (review before committing)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
