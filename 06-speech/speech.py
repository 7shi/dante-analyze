#!/usr/bin/env python
"""
Speech build — Step 2 of the knowledge graph.

Pure code, no LLM. Attributes a SPEAKER to every quote span by joining the column-aware first-person
referents inside each quote's OWN region (quotespans.own_region) onto the registry's canonical nodes
(05-registry/<canticle>.txt). The core attribution shape mirrors 05-registry/measure.py's coverage
probe; this pass adds registry canonicalization (before the uniqueness test), per-span file output,
and a fail-loud structural check.

Pipeline: gather referents (code) -> canonicalize via registry (code) -> per-span first-person
attribution (code) -> render per-canto (code) -> structural check (code).

Speaker rule (the KG plan):
- a UNIQUE canonical referent of a STRONG first-person tag (io/i'/ïo) in the own region -> speaker
  (signal: strong); more than one distinct strong referent -> (unattributed), flag multi(...);
- else a UNIQUE WEAK first-person referent (mi/me/...) -> speaker (signal: weak);
- else (unattributed) (signal: none); flag `plural` if only plural first person was found.
- orthogonal flag `cross-scene` when the span crosses a scene boundary.
Canonicalization runs BEFORE the uniqueness test, so two source spellings of one figure collapse to
one speaker rather than reading as multi. `--raw` skips the registry join (raw norm_labels), for
early testing without a committed registry.

Input:  04-tags/<canticle>/NN.txt   (committed; labels)
        02-markup/<canticle>/NN.txt (number_scene meta + tag_positions/strip_to_source)
        05-registry/<canticle>.txt  (committed; canonical node table) — unless --raw
        dante_corpus               (source text + quote spans)
Output: 06-speech/<canticle>/NN.txt (committed; one line per quote span, depth-first)
"""
import argparse
import re
import sys

from dante_corpus import api

from dante_analyze import (
    SPEECH_DIR, TAGS_DIR,
    read_markup, load_tags, load_scenes, load_registry, raw_to_canonical,
    number_scene, tag_positions, strip_to_source,
    norm_label, fold_key,
    walk_spans, own_region,
    FIRST_PERSON_STRONG, FIRST_PERSON_WEAK, FIRST_PERSON_PLURAL,
)

CANTICLES = ("inferno", "purgatorio", "paradiso")
UNKNOWN = "(unknown)"
UNATTRIBUTED = "(unattributed)"
_WS_RE = re.compile(r"\s+")


def committed_cantos(canticle):
    """Cantos with a committed 04-tags file, in order; the file is the checkpoint."""
    d = TAGS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


def collapse_ws(text):
    """Whitespace-collapsed text, matching strip_to_source's `_append_collapsed` semantics."""
    return _WS_RE.sub(" ", text).strip()


def gather_referents(canticle, canto, markup, tags, cobj, raw2canon):
    """([(line, col, canon, surf_fold)], {line: (s, e)}) for a canto. `canon` is the registry
    canonical label (or, with raw2canon=None, the raw norm_label); a label that maps to nothing
    (only (unknown), dropped by the registry) contributes no referent. Also runs the per-line
    round-trip guard, warning (not aborting) on the documented nested-brace anomaly."""
    referents = []
    scene_of_line = {}
    for (s, e), res in tags.items():
        _text, _k, meta = number_scene(markup, s, e)
        pos = tag_positions(markup, s, e)
        for ln in range(s, e + 1):
            scene_of_line[ln] = (s, e)
            got = collapse_ws(strip_to_source(markup[ln - 1]))
            want = collapse_ws(cobj.line(ln).text)
            if got != want:
                print(f"WARN {canticle} {canto:02d} line {ln}: round-trip mismatch "
                      f"(nested-brace anomaly?)\n  markup-> {got!r}\n  source-> {want!r}",
                      file=sys.stderr)
        for tag_no, raw in res.items():
            nl = norm_label(raw)
            if nl == UNKNOWN:
                continue
            if raw2canon is None:
                canon = nl
            else:
                canon = raw2canon.get(fold_key(nl))
                if canon is None:
                    continue
            line, col = pos[tag_no]
            _kind, surface = meta[tag_no]
            referents.append((line, col, canon, surface.casefold()))
    return referents, scene_of_line


def attribute(span, referents, scene_of_line):
    """(speaker, signal, flags) for one span from the canonical referents in its own region."""
    strong, weak, plural = set(), set(), set()
    for line, col, canon, surf in referents:
        if not own_region(span, line, col):
            continue
        if surf in FIRST_PERSON_STRONG:
            strong.add(canon)
        elif surf in FIRST_PERSON_WEAK:
            weak.add(canon)
        elif surf in FIRST_PERSON_PLURAL:
            plural.add(canon)

    flags = []
    if len(strong) == 1:
        speaker, signal = next(iter(strong)), "strong"
    elif len(strong) > 1:
        speaker, signal = UNATTRIBUTED, "none"
        flags.append(f"multi({';'.join(sorted(strong))})")
    elif len(weak) == 1:
        speaker, signal = next(iter(weak)), "weak"
    else:
        speaker, signal = UNATTRIBUTED, "none"
        if plural:
            flags.append("plural")

    if scene_of_line.get(span.start_line) != scene_of_line.get(span.end_line):
        flags.append("cross-scene")
    return speaker, signal, flags


def render_canto(canticle, canto, raw2canon):
    """(text, [(quote_id, speaker)]) for a canto: the file body plus the emitted span list (for
    the structural check)."""
    markup = read_markup(canticle, canto)
    tags = load_tags(canticle, canto)
    cobj = api.canto(canticle, canto)
    canto_title, _scenes = load_scenes(canticle, canto)

    referents, scene_of_line = gather_referents(canticle, canto, markup, tags, cobj, raw2canon)

    lines = [f"# Canto {canto:02d} — {canto_title}"]
    emitted = []
    for span, _depth in walk_spans(cobj.quotes()):
        speaker, signal, flags = attribute(span, referents, scene_of_line)
        flag_str = ", ".join(flags) if flags else "-"
        lines.append(f"- {span.quote_id} lines {span.start_line}-{span.end_line} "
                     f"| speaker: {speaker} | signal: {signal} | flags: {flag_str}")
        emitted.append((span.quote_id, speaker))
    return "\n".join(lines) + "\n", emitted, cobj


def check_canto(emitted, cobj, registry):
    """Problems with a canto's speech (empty = OK): every quote span emitted exactly once by id;
    every attributed speaker exists in the registry (skipped when registry is None, i.e. --raw)."""
    problems = []
    walked = sorted(span.quote_id for span, _ in walk_spans(cobj.quotes()))
    got = sorted(qid for qid, _ in emitted)
    if walked != got:
        problems.append(f"emitted span ids {got} != quote spans {walked}")
    if registry is not None:
        for qid, speaker in emitted:
            if speaker != UNATTRIBUTED and speaker not in registry:
                problems.append(f"span {qid}: speaker '{speaker}' not a registry node")
    return problems


def main():
    ap = argparse.ArgumentParser(
        description="Speech build (Step 2): speaker per quote span over 04-tags + the registry "
                    "(see 06-speech/README.md).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to build (default: all three)")
    ap.add_argument("--raw", action="store_true",
                    help="emit raw norm_labels instead of registry-canonical speakers (early testing)")
    args = ap.parse_args()

    failed = False
    for canticle in args.canticles:
        cantos = committed_cantos(canticle)
        if not cantos:
            print(f"(skip {canticle}: no committed 04-tags)", file=sys.stderr)
            continue
        raw2canon = None if args.raw else raw_to_canonical(canticle)
        registry = None if args.raw else load_registry(canticle)
        for canto in cantos:
            text, emitted, cobj = render_canto(canticle, canto, raw2canon)
            problems = check_canto(emitted, cobj, registry)
            if problems:
                failed = True
                print(f"\nspeech {canticle} {canto:02d}: {len(problems)} STRUCTURAL problem(s):",
                      file=sys.stderr)
                for p in problems:
                    print(f"- {p}", file=sys.stderr)
                continue
            path = SPEECH_DIR / canticle / f"{canto:02d}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"speech {canticle} {canto:02d}: OK — {len(emitted)} spans", file=sys.stderr)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
