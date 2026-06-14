#!/usr/bin/env python
"""
Registry build — Step 1 of the knowledge graph.

Aggregates the per-scene 04-tags labels into one canonical, source-spelled NODE per figure across
the whole work, with node typing (closed vocabulary), set support, and a per-canticle alias-surface
inventory. This is the node layer the speech/relations passes join onto.

Pipeline: gather (code) -> fold-merge (code) -> set-resolve (code) -> type (LLM, cached) ->
render per-canticle (code) -> structural check (code).

The deterministic code-merge collapses the distinct labels by `fold_key` (canonical = most frequent
original spelling, decided GLOBALLY so a cross-canticle figure shares one label); `measure.py`
already proved this is total and sizes it (2,923 distinct -> 2,712 nodes). The only LLM stage is
node typing (~136 batched calls), checked and retried like `tags.py`.

Decision: epithet grouping is SKIPPED in v1 — every epithet node
stays its own node, flagged `grouped: no`. A flagged singleton is safer than an unverifiable merge;
consolidation is a later pass.

Output `05-registry/<canticle>.txt` (committed). Surfaces and labels are PER-CANTICLE (each file is
self-contained, so the structural check closes within it); the canonical label and type are global,
re-emitted in each canticle file the node appears in. Typing is cached in `05-registry/types.txt`
(`<canonical> = <type>`), appended as batches pass, so the ~136 calls resume.

Input:  04-tags/<canticle>/NN.txt   (committed; run 04-tags/tags.py first)
        02-markup/<canticle>/NN.txt (for number_scene's surface meta)
Output: 05-registry/<canticle>.txt  (committed) + 05-registry/types.txt (typing cache)
"""
import argparse
import re
import sys
from collections import Counter, defaultdict

from dante_analyze import (
    REGISTRY_DIR, TAGS_DIR, MAX_LENGTH,
    read_markup, load_tags, number_scene,
    norm_label, fold_key, split_set, is_capitalized_name,
    call_llm, step_sep,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
UNKNOWN = "(unknown)"
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"
TYPES = ("individual", "generic", "class", "hypothetical-simile", "non-person")
BATCH = 20
TYPES_CACHE = REGISTRY_DIR / "types.txt"


def committed_cantos(canticle):
    """Cantos with a committed 04-tags file, in order; the file is the checkpoint."""
    d = TAGS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


# ---------- 1-2. gather + code-merge (pure code) ----------

class Nodes:
    """The code-merged node set over all three canticles. `key` is fold_key(canonical).

    - labels[key]: global Counter of norm_label spellings -> canonical (most frequent, tie by spelling)
    - labels_canticle[key][canticle]: Counter of spellings that occurred in that canticle
    - surfaces[key][canticle]: Counter of marked surface forms -> counts (per canticle)
    `(unknown)` is excluded from nodes (exempt from the assignment check, as in measure.py).
    """

    def __init__(self, canticles):
        self.labels = defaultdict(Counter)
        self.labels_canticle = defaultdict(lambda: defaultdict(Counter))
        self.surfaces = defaultdict(lambda: defaultdict(Counter))
        self.distinct_canticle = defaultdict(set)   # canticle -> {norm_label} (for the check)
        for canticle in canticles:
            self._gather(canticle)

    def _gather(self, canticle):
        for canto in committed_cantos(canticle):
            markup = read_markup(canticle, canto)
            tags = load_tags(canticle, canto)
            for (s, e), res in tags.items():
                _text, _k, meta = number_scene(markup, s, e)
                for tag_no, raw in res.items():
                    nl = norm_label(raw)
                    if nl == UNKNOWN:
                        continue
                    key = fold_key(nl)
                    self.labels[key][nl] += 1
                    self.labels_canticle[key][canticle][nl] += 1
                    self.distinct_canticle[canticle].add(nl)
                    _kind, surface = meta[tag_no]
                    self.surfaces[key][canticle][surface] += 1

    def canonical(self, key):
        """Most frequent global spelling of the node (tie broken by spelling)."""
        return max(self.labels[key].items(), key=lambda kv: (kv[1], kv[0]))[0]

    @property
    def canonicals(self):
        return {self.canonical(k) for k in self.labels}

    def members(self, key):
        """Set members if the node's canonical label is a comma-set, else None."""
        return split_set(self.canonical(key), self.canonicals)

    def keys_in(self, canticle):
        """Node keys occurring in `canticle`, sorted by descending in-canticle count then label."""
        keys = [k for k in self.labels if canticle in self.labels_canticle[k]]
        return sorted(keys, key=lambda k: (-sum(self.surfaces[k][canticle].values()),
                                           self.canonical(k)))


# ---------- 3. node typing (LLM, cached) ----------

TYPE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*=\s*([a-z-]+)\s*$")


def load_types_cache():
    """{canonical: type} already decided, from the resume cache."""
    out = {}
    if TYPES_CACHE.exists():
        for line in TYPES_CACHE.read_text(encoding="utf-8").splitlines():
            if " = " in line:
                label, _, t = line.rpartition(" = ")
                out[label.strip()] = t.strip()
    return out


def append_types_cache(typed):
    """Append `{canonical: type}` to the resume cache."""
    with TYPES_CACHE.open("a", encoding="utf-8") as f:
        for label, t in typed.items():
            f.write(f"{label} = {t}\n")


def build_typing_prompt(batch):
    """Type each label with the closed vocabulary. Only the labels are sent — no glosses, no
    per-item answers. The vocabulary definitions are general knowledge."""
    listing = "\n".join(f"{i}. {label}" for i, label in enumerate(batch, 1))
    return f"""Each line below is a label naming a figure referred to in Dante's Divine Comedy, in
source (Italian) spelling. Classify EACH with exactly one type from this closed vocabulary:

- individual        — a specific, identifiable person or being (e.g. a named soul, a named angel).
- generic           — an unspecified person referred to in general terms ("anyone", "a soul").
- class             — a category or kind of being, not one specific member (an order of angels, a
                      group of sinners taken as a type).
- hypothetical-simile — a figure that exists only inside a simile or hypothetical comparison
                      ("like a man who...").
- non-person        — not a person: a personification, an abstraction, a place, an animal, a
                      celestial body, or an object treated as a referent.

Labels:
{listing}

Output one numbered line per label, in the SAME order, exactly:

    n. <label> = <type>

Echo the label VERBATIM (same spelling) and put one type from the vocabulary after the `=`. Output
only these {len(batch)} lines and nothing else."""


def build_typing_retry(problems, batch):
    issues = "\n".join(f"- {p}" for p in problems)
    listing = "\n".join(f"{i}. {label}" for i, label in enumerate(batch, 1))
    return f"""The classification did not pass the check:
{issues}

Produce it again. One line `n. <label> = <type>` per label, same order, label echoed verbatim, type
from: {", ".join(TYPES)}. The labels:
{listing}
Output only these {len(batch)} lines and nothing else."""


def parse_typing(text, batch):
    """{label: type} from the reply, keyed by the echoed label matched against `batch` by index."""
    out = {}
    for raw in text.splitlines():
        m = TYPE_RE.match(raw)
        if not m:
            continue
        n, label, t = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
        if 1 <= n <= len(batch):
            out[batch[n - 1]] = t
    return out


def check_typing(typed, batch):
    """Problems with a batch's typing (empty = OK): every label typed once, type in vocabulary."""
    problems = []
    for label in batch:
        if label not in typed:
            problems.append(f"missing type for '{label}'")
        elif typed[label] not in TYPES:
            problems.append(f"'{label}' has type '{typed[label]}' not in {', '.join(TYPES)}")
    return problems


def type_batch(batch, model, max_attempts=3):
    """Type one batch, retrying in-conversation until the check passes or attempts run out;
    the last draft is kept (any still-bad label falls back to '(untyped)', flagged)."""
    messages = [{"role": "user", "content": build_typing_prompt(batch)}]
    step_sep("registry typing")
    resp = call_llm(messages, model, include_thoughts=True)
    typed = parse_typing(resp.text, batch)
    for attempt in range(1, max_attempts + 1):
        problems = check_typing(typed, batch)
        if not problems:
            return typed
        print(f"typing batch: attempt {attempt}/{max_attempts}: {len(problems)} problem(s):",
              file=sys.stderr)
        for p in problems:
            print(f"- {p}", file=sys.stderr)
        if attempt >= max_attempts:
            break
        messages = messages + [
            {"role": "assistant", "content": resp.text},
            {"role": "user", "content": build_typing_retry(problems, batch)},
        ]
        resp = call_llm(messages, model, max_length=MAX_LENGTH, include_thoughts=True)
        typed = parse_typing(resp.text, batch)
    print(f"typing batch: NOT resolved after {max_attempts} attempt(s); flagging '(untyped)'",
          file=sys.stderr)
    return {label: typed.get(label) if typed.get(label) in TYPES else "(untyped)"
            for label in batch}


def type_nodes(nodes, model):
    """Type every non-set node once (global), using the resume cache to skip typed labels."""
    cache = load_types_cache()
    to_type = []
    for key in nodes.labels:
        if nodes.members(key) is not None:   # sets are not typed (set is a structural kind)
            continue
        canonical = nodes.canonical(key)
        if canonical not in cache:
            to_type.append(canonical)
    print(f"typing: {len(to_type)} node(s) to type, {len(cache)} cached", file=sys.stderr)
    for i in range(0, len(to_type), BATCH):
        batch = to_type[i:i + BATCH]
        typed = type_batch(batch, model)
        append_types_cache(typed)
        cache.update(typed)
        print(f"typing: {min(i + BATCH, len(to_type))}/{len(to_type)} done", file=sys.stderr)
    return cache


# ---------- 4. render per-canticle (pure code) ----------

def render_node(nodes, key, canticle, types):
    """The `## <canonical>` block for a node as it appears in `canticle`."""
    canonical = nodes.canonical(key)
    members = nodes.members(key)
    lines = [f"## {canonical}"]
    if members is not None:
        lines.append("- type: set")
        lines.append(f"- members: {' | '.join(members)}")
        return "\n".join(lines)
    lines.append(f"- type: {types.get(canonical, '(untyped)')}")
    # per-canticle labels, canonical heading first, then others by descending count
    spellings = nodes.labels_canticle[key][canticle]
    others = sorted((s for s in spellings if s != canonical),
                    key=lambda s: (-spellings[s], s))
    labels = [canonical] + others   # global canonical heads the per-canticle spellings
    lines.append(f"- labels: {' | '.join(labels)}")
    surf = nodes.surfaces[key][canticle]
    surf_str = ", ".join(f"{s} ({n})" for s, n in
                         sorted(surf.items(), key=lambda kv: (-kv[1], kv[0])))
    lines.append(f"- surfaces: {surf_str}")
    if not is_capitalized_name(canonical):   # option A: epithet layer not consolidated
        lines.append("- grouped: no")
    return "\n".join(lines)


def render_canticle(nodes, canticle, types):
    parts = [f"# Registry — {canticle}\n"]
    for key in nodes.keys_in(canticle):
        parts.append(render_node(nodes, key, canticle, types) + "\n")
    return "\n".join(parts)


# ---------- 5. structural check (write time) ----------

def check_registry(nodes, canticle, types):
    """Problems with a rendered canticle (empty = OK): every distinct 04-tags label in the
    canticle assigned to exactly one node's labels
    (`(unknown)` already excluded); every set member resolves to a node; every type in
    vocabulary; canonical heading is one of its group's raw labels."""
    problems = []
    assigned = Counter()
    for key in nodes.keys_in(canticle):
        canonical = nodes.canonical(key)
        if canonical not in nodes.labels[key]:
            problems.append(f"{canonical}: heading not among its group's raw labels")
        for nl in nodes.labels_canticle[key][canticle]:
            assigned[nl] += 1
        members = nodes.members(key)
        if members is not None:
            # A member either folds onto a standalone node or is a bare capitalized name that
            # appears only inside the set (no own node) — split_set's admission contract. A
            # member that is neither would be a malformed set (a lowercase clause); flag it.
            for m in members:
                if fold_key(m) not in nodes.labels and not is_capitalized_name(m):
                    problems.append(f"{canonical}: set member '{m}' is not a node or a name")
        else:
            t = types.get(canonical, "(untyped)")
            if t not in TYPES:
                problems.append(f"{canonical}: type '{t}' not in vocabulary")
    for nl in nodes.distinct_canticle[canticle]:
        if assigned[nl] != 1:
            problems.append(f"label '{nl}' assigned to {assigned[nl]} nodes (expected 1)")
    return problems


# ---------- driver ----------

def main():
    ap = argparse.ArgumentParser(
        description="Registry build (Step 1): canonical node table over 04-tags "
                    "(see 05-registry/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to build (default: all three; canonical labels are global)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"LLM for node typing (default: {DEFAULT_MODEL})")
    args = ap.parse_args()

    # canonical labels are decided globally — always gather all three so a cross-canticle
    # figure shares one label, even when only one canticle is being (re)rendered.
    nodes = Nodes(CANTICLES)
    print(f"code-merge: {sum(len(c) for c in nodes.labels.values())} label spellings -> "
          f"{len(nodes.labels)} nodes", file=sys.stderr)

    types = type_nodes(nodes, args.model)

    failed = False
    for canticle in args.canticles:
        if canticle not in nodes.distinct_canticle:
            print(f"(skip {canticle}: no committed 04-tags)", file=sys.stderr)
            continue
        problems = check_registry(nodes, canticle, types)
        if problems:
            failed = True
            print(f"\nregistry {canticle}: {len(problems)} STRUCTURAL problem(s):", file=sys.stderr)
            for p in problems:
                print(f"- {p}", file=sys.stderr)
            continue
        path = REGISTRY_DIR / f"{canticle}.txt"
        path.write_text(render_canticle(nodes, canticle, types), encoding="utf-8")
        n = len(nodes.keys_in(canticle))
        print(f"registry {canticle}: OK — {n} nodes written to {path}", file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
