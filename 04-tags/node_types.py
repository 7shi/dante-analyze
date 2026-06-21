#!/usr/bin/env python
"""Node typing — the closed-vocabulary classification of every figure label, cached in
`04-tags/types.txt`.

Each canonical 04-tags label (the most frequent spelling in its `fold_key` group) is typed once,
GLOBALLY, with the closed vocabulary `TYPES` (individual / generic / class / hypothetical-simile /
non-person / deictic). Scene-local demonstrative/periphrastic labels (`quel cane`, `colui che …`)
are typed `deictic` DETERMINISTICALLY (is_deictic) — never sent to the model — and dropped from the
cast/cohort downstream. The model types only the rest. `types.txt` is written as `<canonical> = <type>`.

Why this is a 04-tags step, run BEFORE coreference and the registry:

- Typing is **overlay-free**: a label's type is a function of the label string alone, so this gathers
  the RAW committed labels (`Nodes(..., apply_coref=False)`). The cache is reconciled to the current
  node set and rewritten whole each run (resume reuses cached types, so the model never re-types a
  known label; per-batch appends keep a crashed run resumable). The whole-file rewrite drops labels
  no longer present — a decomposed mixed-bundle heading, or a label reclassified to `deictic`. The
  overlay-free property (what coreference depends on) is unchanged.
- The coreference generator (`04-tags/coreference.py`) needs `types.txt` to pick candidate targets
  (it merges under-specified `individual` labels into fuller `individual` ones). If typing were a
  side effect of the registry build, coref would need a registry build first, and the registry render
  consumes coref's overlay — the old `registry -> coref -> registry` cycle. Producing `types.txt`
  here, from 04-tags alone, makes the pipeline linear:

      tags.py -> node_types.py (types.txt) -> coreference.py (coref.txt) -> 05-registry/registry.py

  The registry then only READS `types.txt` (via `load_types_cache`) and renders once — no model call,
  no back-edge into 04-tags.

Run it as ONE process (`node_types.py inferno purgatorio paradiso`); `types.txt` is a global append-only
file with no locking, so a second concurrent process corrupts the cache.

Input:  04-tags/<canticle>/NN.txt   (committed; run 04-tags/tags.py first)
Output: 04-tags/types.txt           (typing cache; committed)
"""
import argparse
import re
import sys

from dante_analyze import (
    MAX_LENGTH, TYPES_CACHE,
    Nodes, TYPES, is_deictic,
    load_types_cache, call_llm, step_sep,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
DEFAULT_MODEL = "ollama:gemma4:31b-it-qat"
BATCH = 20

TYPE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*=\s*([a-z-]+)\s*$")


def append_types_cache(typed):
    """Append `{canonical: type}` to the resume cache (04-tags/types.txt), crash-safe within a run."""
    with TYPES_CACHE.open("a", encoding="utf-8") as f:
        for label, t in typed.items():
            f.write(f"{label} = {t}\n")


def write_types_cache(types):
    """Rewrite the WHOLE typing cache (04-tags/types.txt), sorted, so the file reflects EXACTLY the
    current node set: stale lines (decomposed-bundle headings, labels reclassified to `deictic`) are
    dropped. Called once at the end; per-batch appends during the run keep resume crash-safe."""
    lines = [f"{label} = {t}" for label, t in sorted(types.items())]
    TYPES_CACHE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


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
    step_sep("node typing")
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
    """Type every non-set node once and return `{canonical: type}` for the CURRENT node set only.

    Deictic labels (is_deictic) are assigned `deictic` DETERMINISTICALLY — never sent to the model,
    overriding any stale cached `individual`. The rest are reused from the resume cache (no
    re-typing) or, if new (e.g. a collective remainder a mixed bundle just promoted), typed by the
    model. Returns the reconciled set; the caller writes the whole cache so dropped labels disappear."""
    cache = load_types_cache()
    result = {}
    to_type = []
    for key in nodes.labels:
        if nodes.members(key) is not None:   # sets are not typed (set is a structural kind)
            continue
        canonical = nodes.canonical(key)
        if is_deictic(canonical):
            result[canonical] = "deictic"    # deterministic; scene-local deixis, not a stable figure
        elif canonical in cache:
            result[canonical] = cache[canonical]
        else:
            to_type.append(canonical)
    print(f"typing: {len(to_type)} node(s) to type, {len(result)} from cache/deterministic",
          file=sys.stderr)
    for i in range(0, len(to_type), BATCH):
        batch = to_type[i:i + BATCH]
        typed = type_batch(batch, model)
        append_types_cache(typed)         # crash-safe resume; the final whole-file write cleans up
        result.update(typed)
        print(f"typing: {min(i + BATCH, len(to_type))}/{len(to_type)} done", file=sys.stderr)
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Node typing (KG identity prep): classify every 04-tags label with the closed "
                    "vocabulary into 04-tags/types.txt (see 05-registry/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to gather (default: all three; canonical labels are global)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"LLM for node typing (default: {DEFAULT_MODEL})")
    args = ap.parse_args()

    # Canonical labels are decided globally — always gather all three so a cross-canticle figure
    # shares one label. Overlay-free (apply_coref=False): types.txt must be a superset of every raw
    # label, independent of the coreference overlay (which is generated AFTER this step).
    nodes = Nodes(CANTICLES, apply_coref=False)
    print(f"code-merge: {sum(len(c) for c in nodes.labels.values())} label spellings -> "
          f"{len(nodes.labels)} nodes", file=sys.stderr)

    types = type_nodes(nodes, args.model)
    write_types_cache(types)              # whole-file rewrite: drop stale/decomposed/reclassified
    print(f"typing: done — {len(types)} typed label(s) in {TYPES_CACHE}", file=sys.stderr)


if __name__ == "__main__":
    main()
