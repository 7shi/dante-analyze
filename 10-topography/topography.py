#!/usr/bin/env python
"""
Topography build — context-lock Step 2, the place analogue of 05-registry.

09-location emits, per scene, the current-setting SURFACE the source uses (`it`), deliberately
noisy: across 100 cantos 371 naming lines use 337 distinct surfaces. This pass folds those surfaces
into a small set of canonical REGIONS and produces a piecewise-constant region sequence — one region
per scene — the macro where-layer the action-only KG (08-kg) lacks.

The journey is (almost) monotonic, so region identity is POSITIONAL: a "ripa" in canto 4 is not the
"ripa" in canto 31. The pass therefore walks the canticle in journey order and asks one narrow
judgment per canto — for each newly named place-term, has the journey moved on to a NEW major
stretch, or is this still the SAME stretch? Because every comparison is only against the CURRENT
region, a far-off canto can never be merged back into an early one: the region sequence is
piecewise-constant by construction.

Naming is code, not LLM (the 05-registry split: deterministic merge, model residual). The model
only decides boundaries (same/new); code names each region from its member surfaces (most frequent,
ties broken by earliest appearance), so a coined or unrepresentative label cannot leak in.

Per the repository premise the prompt names no circle / terrace / sphere and fixes no region count —
the poem's known structure is the EVALUATION target, never an input.

Pipeline (per canto, journey order): build terms (code) -> same/new boundary (LLM, cached) ->
name + sequence + render per-canticle (code) -> structural check (code).

Regions are per-canticle, so the walk and its resume cache `10-topography/<canticle>.clusters.txt`
(`<canto>:<occ> <surface> = <region-key>`) are per-canticle; the cache replays deterministically.

Input:  09-location/<canticle>/NN.txt  (committed; run 09-location/location.py first)
Output: 10-topography/<canticle>.txt   (committed; the region registry + sequence runs)
        10-topography/<canticle>.clusters.txt  (resume cache)
"""
import argparse
import re
import sys
from collections import Counter, OrderedDict

from dante_analyze import (
    TOPOGRAPHY_DIR, MAX_LENGTH,
    available_cantos, load_locations, norm_label,
    call_llm, step_sep,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"
UNSTATED = "(unstated)"   # sentinel region for scenes before any place is named (Paradiso prologue)


# ---------- 1. build per-canto terms (pure code) ----------

def canto_terms(canticle, canto):
    """The named place-terms of a canto, in journey order, plus per-scene structure.

    Returns (terms, scenes): `terms` is [(surface, en)] for each location line whose `it` is not `-`
    (term index = `occ`); `scenes` is [(s, e, first_named, occs)] in scene order, where `first_named`
    is True iff the scene's primary (first) location line names a place, and `occs` are the term
    indices the scene contributes (its named lines, primary then movement)."""
    locs = load_locations(canticle, canto)
    terms = []
    scenes = []
    for (s, e) in sorted(locs):
        scene_locs = locs[(s, e)]
        first_named = bool(scene_locs) and scene_locs[0]["it"] != "-"
        occs = []
        for loc in scene_locs:
            if loc["it"] != "-":
                occs.append(len(terms))
                terms.append((norm_label(loc["it"]), loc["en"]))
        scenes.append((s, e, first_named, occs))
    return terms, scenes


# ---------- 2. same/new boundary (LLM, cached) ----------

WALK_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*=\s*(same|new)\s*$", re.I)
CACHE_RE = re.compile(r"^(?P<canto>\d+):(?P<occ>\d+)\s+(?P<surf>.*\S)\s*=\s*(?P<key>r\d+)\s*$")


def cache_path(canticle):
    return TOPOGRAPHY_DIR / f"{canticle}.clusters.txt"


def load_walk_cache(canticle):
    """{(canto, occ): region_key} already decided, from the resume cache."""
    out = {}
    path = cache_path(canticle)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = CACHE_RE.match(line)
            if m:
                out[(int(m.group("canto")), int(m.group("occ")))] = m.group("key")
    return out


def append_walk_cache(canticle, canto, terms, keys):
    path = cache_path(canticle)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for occ, ((surf, _en), key) in enumerate(zip(terms, keys)):
            f.write(f"{canto}:{occ} {surf} = {key}\n")


def describe_current(region_members):
    """The entering region as a short cue for the prompt: its member place-terms."""
    if not region_members:
        return "(the journey is just beginning — no region entered yet)"
    return ", ".join(region_members)


def build_walk_prompt(terms, current_members):
    """One judgment: segment this canto's place-terms into major stretches. Reading the ordered list
    top to bottom, each term either continues the SAME stretch as the term just above it or begins a
    NEW one (the first term continues the region currently occupied, or begins a new one). Only the
    source terms and glosses are sent, plus the place-terms of the region currently occupied — no
    per-item answers, no naming of the poem's known structure (the evaluation target, not an input)."""
    listing = "\n".join(f"{i}. {surf}  ({en})" for i, (surf, en) in enumerate(terms, 1))
    return f"""The travellers move through Dante's Divine Comedy in one continuous journey. The region
they are in as this canto opens is named in the source by these place-terms:

  {describe_current(current_members)}

Below are the place-terms the source names next, IN ORDER, as the canto proceeds (Italian, with a
short English gloss). A major region is one stretch the travellers occupy continuously before moving
on. The SAME stretch is usually named by several consecutive terms (the place, the ground under it,
a river or wall seen from it, a sub-spot within it), so expect long runs of `same`; the travellers
move to a genuinely new stretch only occasionally.

Read top to bottom. For EACH term mark:
- `same` — names the SAME stretch as the term immediately above it (for term 1: the same stretch as
  the region the canto opens in, shown above);
- `new`  — a different major stretch BEGINS here (the travellers have moved on from the term above).

Terms:
{listing}

Output one numbered line per term, in the SAME order, exactly:

    n. <term> = same
    n. <term> = new

Echo the term VERBATIM. Judge only from the terms, glosses, and their order — do not rely on outside
knowledge of the poem's structure. Output only these {len(terms)} lines and nothing else."""


def build_walk_retry(problems, terms, current_members):
    issues = "\n".join(f"- {p}" for p in problems)
    listing = "\n".join(f"{i}. {surf}  ({en})" for i, (surf, en) in enumerate(terms, 1))
    return f"""The segmentation did not pass the check:
{issues}

Produce it again. One line `n. <term> = same` or `n. <term> = new` per term, same order, term echoed
verbatim. `same` = same stretch as the term just above (term 1: as the region the canto opens in);
`new` = a new stretch begins here. The region the canto opens in: {describe_current(current_members)}.
The terms:
{listing}
Output only these {len(terms)} lines and nothing else."""


def parse_walk(text, terms):
    """{occ: 'same'|'new'} from the reply, keyed by index against `terms`."""
    out = {}
    for raw in text.splitlines():
        m = WALK_RE.match(raw)
        if not m:
            continue
        n, d = int(m.group(1)), m.group(3).lower()
        if 1 <= n <= len(terms):
            out[n - 1] = d
    return out


def check_walk(decisions, terms):
    """Problems with a canto's marking (empty = OK): every term decided once as same|new."""
    return [f"missing same/new for term {i + 1} ('{terms[i][0]}')"
            for i in range(len(terms)) if i not in decisions]


def walk_canto(terms, current_members, model, max_attempts=3):
    """{occ: 'same'|'new'} for a canto, retried in-conversation until the check passes or attempts
    run out; the last draft is kept (any still-missing term falls back to 'new', flagged)."""
    messages = [{"role": "user", "content": build_walk_prompt(terms, current_members)}]
    step_sep("topography walk")
    resp = call_llm(messages, model)
    decisions = parse_walk(resp.text, terms)
    for attempt in range(1, max_attempts + 1):
        problems = check_walk(decisions, terms)
        if not problems:
            return decisions
        print(f"walk canto: attempt {attempt}/{max_attempts}: {len(problems)} problem(s):",
              file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": resp.text},
            {"role": "user", "content": build_walk_retry(problems, terms, current_members)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH)
        decisions = parse_walk(resp.text, terms)
    print(f"walk canto: NOT resolved after {max_attempts} attempt(s); flagging missing as 'new'",
          file=sys.stderr)
    return {i: decisions.get(i, "new") for i in range(len(terms))}


# ---------- 3. drive the walk, name regions, build sequence (pure code) ----------

class Walk:
    """The journey walk over one canticle. Accumulates regions in journey order; each region holds
    a Counter of member surfaces and the global order in which each was first seen (for naming).
    `key_of[(canto, occ)]` is the region-key of every named term."""

    def __init__(self):
        self.members = OrderedDict()      # region_key -> Counter(surface -> count)
        self.first_seen = {}              # (region_key, surface) -> global order
        self.key_of = {}                  # (canto, occ) -> region_key
        self.current = None               # current region_key (carried across cantos)
        self._next = 1
        self._order = 0

    def keys_from_decisions(self, decisions, n):
        """Turn a canto's per-term same/new into region-keys, opening a region on each `new` (or at
        the very start). The current region carries in from the previous canto."""
        keys = []
        ck, idx = self.current, self._next
        for i in range(n):
            if decisions[i] == "new" or ck is None:
                ck = f"r{idx}"
                idx += 1
            keys.append(ck)
        return keys

    def apply(self, canto, terms, keys):
        """Record a canto's region-keys: count members, set key_of, advance current/next."""
        for occ, ((surf, _en), key) in enumerate(zip(terms, keys)):
            self.members.setdefault(key, Counter())[surf] += 1
            self.first_seen.setdefault((key, surf), self._order)
            self._order += 1
            self.key_of[(canto, occ)] = key
            self.current = key
        seen = [int(k[1:]) for k in keys]
        if seen:
            self._next = max(self._next, max(seen) + 1)

    def label(self, key):
        """The canonical region label: the most frequent member surface, ties broken by earliest
        appearance (05-registry's canonical-from-observed rule, applied to places)."""
        members = self.members[key]
        return max(members, key=lambda s: (members[s], -self.first_seen[(key, s)]))


def run_walk(canticle, model):
    """Walk the canticle, using the resume cache for already-decided cantos. Returns the Walk."""
    cache = load_walk_cache(canticle)
    walk = Walk()
    for canto in available_cantos(canticle):
        terms, _scenes = canto_terms(canticle, canto)
        if not terms:
            continue
        cached = [cache.get((canto, occ)) for occ in range(len(terms))]
        if all(k is not None for k in cached):
            keys = cached
        else:
            current_members = list(walk.members.get(walk.current, ())) if walk.current else []
            decisions = walk_canto(terms, current_members, model)
            keys = walk.keys_from_decisions(decisions, len(terms))
            append_walk_cache(canticle, canto, terms, keys)
        walk.apply(canto, terms, keys)
    return walk


def build_sequence(canticle, walk):
    """The per-scene region sequence in journey order: [(canto, s, e, region_key)]. A scene whose
    primary line names a place takes that term's region; a carried scene inherits the running
    region; each scene's last named term updates the carry (in-scene movement)."""
    seq = []
    carry = None
    for canto in available_cantos(canticle):
        _terms, scenes = canto_terms(canticle, canto)
        for (s, e, first_named, occs) in scenes:
            region = walk.key_of[(canto, occs[0])] if first_named else carry
            if occs:
                carry = walk.key_of[(canto, occs[-1])]
            seq.append((canto, s, e, region))
    return seq


def build_runs(seq):
    """The piecewise-constant sequence as runs [(region_key, canto, ls, le)]; consecutive scenes
    sharing a region within one canto merge. A leading carried region of None is the `(unstated)`
    sentinel."""
    runs = []
    for canto, s, e, region in seq:
        key = region if region is not None else UNSTATED
        if runs and runs[-1][0] == key and runs[-1][1] == canto:
            r, c, ls, _le = runs[-1]
            runs[-1] = (r, c, ls, e)
        else:
            runs.append((key, canto, s, e))
    return runs


# ---------- 4. render + structural check (pure code) ----------

def render_canticle(canticle, walk, runs):
    """Render 10-topography/<canticle>.txt: one block per region in first-appearance order, with its
    English gloss, member surfaces (with counts), and its runs. Region-keys become code-chosen
    labels; the `(unstated)` sentinel renders as-is."""
    en_of = {}
    for canto in available_cantos(canticle):
        terms, _ = canto_terms(canticle, canto)
        for occ, (surf, en) in enumerate(terms):
            en_of.setdefault(surf, en)

    runs_by_key = OrderedDict()
    for key, canto, ls, le in runs:
        runs_by_key.setdefault(key, []).append((canto, ls, le))

    # Two distinct stretches can share their most-frequent surface (e.g. two Malebolge bridges both
    # named "lo scoglio"); disambiguate in journey order so every region heading is unique and the
    # load_topography contract (one region per heading) holds.
    used = Counter()
    label_of = {}
    for key in runs_by_key:
        if key == UNSTATED:
            continue
        base = walk.label(key)
        used[base] += 1
        label_of[key] = base if used[base] == 1 else f"{base} #{used[base]}"

    parts = [f"# Topography — {canticle}\n"]
    for key in runs_by_key:
        run_str = ", ".join(f"{c}:{ls}-{le}" for c, ls, le in runs_by_key[key])
        if key == UNSTATED:
            parts.append(f"## {UNSTATED}\n- en: not stated\n- surfaces: -\n- runs: {run_str}\n")
            continue
        label = label_of[key]
        en_label = walk.label(key)
        members = walk.members[key]
        surf_str = ", ".join(f"{s} ({members[s]})" for s in
                             sorted(members, key=lambda s: (-members[s], walk.first_seen[(key, s)])))
        parts.append(f"## {label}\n- en: {en_of.get(en_label, '-')}\n"
                     f"- surfaces: {surf_str}\n- runs: {run_str}\n")
    return "\n".join(parts)


def check_topography(canticle, walk, runs):
    """Problems with a built canticle. Fatal (empty = OK): every named term has a region-key (the
    sequence is then total by construction). Soft (warnings only, kept): a region recurring after
    another intervenes — by construction the walk is piecewise-constant, so any such note flags a
    real anomaly."""
    problems = []
    for canto in available_cantos(canticle):
        terms, _ = canto_terms(canticle, canto)
        for occ in range(len(terms)):
            if (canto, occ) not in walk.key_of:
                problems.append(f"canto {canto} term {occ} has no region")

    order = []
    for key, _c, _ls, _le in runs:
        if not order or order[-1] != key:
            order.append(key)
    for key, n in Counter(order).items():
        if n > 1:
            label = UNSTATED if key == UNSTATED else walk.label(key)
            print(f"topography {canticle}: NOTE region '{label}' recurs after another region "
                  f"intervenes — unexpected for a monotonic walk", file=sys.stderr)
    return problems


# ---------- driver ----------

def main():
    ap = argparse.ArgumentParser(
        description="Topography build (context-lock Step 2): walk each canticle in journey order, "
                    "folding 09-location surfaces into a piecewise-constant region sequence "
                    "(see 10-topography/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to build (default: all three)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"LLM for the same/new boundary judgment (default: {DEFAULT_MODEL})")
    args = ap.parse_args()

    failed = False
    for canticle in args.canticles:
        if not available_cantos(canticle):
            print(f"(skip {canticle}: no committed 09-location)", file=sys.stderr)
            continue
        walk = run_walk(canticle, args.model)
        seq = build_sequence(canticle, walk)
        runs = build_runs(seq)
        problems = check_topography(canticle, walk, runs)
        if problems:
            failed = True
            print(f"\ntopography {canticle}: {len(problems)} STRUCTURAL problem(s):", file=sys.stderr)
            for p in problems:
                print(f"- {p}", file=sys.stderr)
            continue
        path = TOPOGRAPHY_DIR / f"{canticle}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_canticle(canticle, walk, runs), encoding="utf-8")
        n_regions = len({r[0] for r in runs})
        print(f"topography {canticle}: OK — {n_regions} regions over {len(runs)} runs written to {path}",
              file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
