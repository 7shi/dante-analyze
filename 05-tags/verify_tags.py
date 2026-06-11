"""
Post-run verification for the `05-tags/` resolution tables (analysis-layer check, no LLM).

Two independent checks, per scene, across whole canticles:

1. COUNT — does `05-tags/<c>/NN.txt` resolve exactly the tags the scene has? The authoritative
   count is `k` from `scenelib.number_scene` on the NN markup (the same numbering tags.py
   itself used). We also parse the tag numbers the committed `03-reading/<c>/NN.txt` lists under
   `**Tag Resolutions:**`. A scene passes when reading's tag-number set, tags' `n.` line set,
   and `{1..k}` all agree. Any gap, extra, or count mismatch between the three is reported.

2. ELISION — does a `05-tags/` label contain the known over-correction where the de-elision rule
   un-elided a grammatically REQUIRED elision (`l'altra` written as `la altra`)? We flag an
   article/demonstrative token immediately followed by a vowel-initial word — cases Italian
   always elides. These are CANDIDATES for review, not hard errors (this is a documented
   residual of the completed run; see PLAN.md "Known residual").

With `--fix`, the elision candidates are not just reported but REPAIRED IN PLACE: every
`n. Name` label in the committed `05-tags/` files is rewritten through `scenelib.fix_elision`
(`la altra` -> `l'altra`, apostrophe U+0027), leaving everything else byte-for-byte. The fix
runs first, then the normal checks report the post-fix state (so ELISION should then read 0).

Exit status: non-zero if any COUNT problem is found (a structural defect). Elision candidates
are warnings and do NOT fail the run unless `--strict` is given.

Usage:
    uv run verify_tags.py inferno purgatorio paradiso
    uv run verify_tags.py inferno -c 1          # one canto
    uv run verify_tags.py inferno --strict      # also fail on elision candidates
    uv run verify_tags.py inferno --fix         # repair elisions in the committed 05-tags/ files
"""
import argparse
import re
import sys

from dante_analyze import (
    MARKUP_DIR, READING_DIR, TAGS_DIR, ELIDE_RE, TAGS_LINE_RE, fix_elision, load_scenes,
    read_markup, number_scene, out_path, scene_bodies,
)

# A reading resolution line. Both the section HEADER ("Tag Resolutions" /
# "Resolution of Numbered Tags" / …) and the per-tag line markup vary across cantos —
# `` * `[3:i']`: Dante ``, `- **[1]**: …`, `*   **[1]** (`+io`): …`, `{4:Iulio}: …` — so
# instead of locating the header we match any LINE that BEGINS (after list bullets / bold /
# backtick) with a tag token `[n…]` or `{n…}`, and take its number. Prose lines start with a
# word, not a bracket, so they don't match. (A `[1-8]`-range line would under-count, but the
# markup `k` is the authoritative count and the cross-check below would flag the discrepancy.)
READING_TAG_LINE_RE = re.compile(r"^[\s>*+\-•]*(?:\*\*|`)?\s*[\[{]\s*\d+\s*[:\]}]")
# One tag token anywhere on such a line — a single resolution line may cover several tags at
# once, e.g. ``**[7:si] / [8:+essi]**: …``, so we collect ALL of them, not just the leading one.
READING_TAG_TOKEN_RE = re.compile(r"[\[{]\s*(\d+)\s*[:\]}]")

def reading_tag_numbers(body):
    """Set of tag numbers the reading scene body resolves — every line that begins with a
    `[n…]`/`{n…}` tag token (the resolution lines, whatever the section header). Empty set
    if the scene lists none."""
    nums = set()
    for line in body.splitlines():
        if READING_TAG_LINE_RE.match(line):
            nums.update(int(n) for n in READING_TAG_TOKEN_RE.findall(line))
    return nums


def tags_resolution(body):
    """{tag_no: name} from a tags scene body's `n. Name` lines, AS COMMITTED (no elision
    fix) — verify_tags reports on the raw labels, so it can still flag the over-correction."""
    out = {}
    for line in body.splitlines():
        m = TAGS_LINE_RE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def cantos_for(canticle):
    """Canto numbers that have a committed tags file, in order."""
    d = TAGS_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(p.stem) for p in d.glob("[0-9][0-9].txt"))


def markup_k(canticle, canto, lines, s, e):
    """Authoritative tag count for a scene from the NN markup, or None if markup absent."""
    if lines is None:
        return None
    _, k, _ = number_scene(lines, s, e)
    return k


def fix_file(path):
    """Re-elide every `n. Name` label in a committed tags canto file IN PLACE. Only the label
    of a matching line changes (via `scenelib.fix_elision`); headers, blank lines, and the
    file's trailing newline are preserved byte-for-byte. Returns the number of labels changed."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")   # keeps the trailing "" if text ended with "\n"
    changed = 0
    for i, line in enumerate(lines):
        m = TAGS_LINE_RE.match(line)
        if m:
            fixed = fix_elision(m.group(2))
            if fixed != m.group(2):
                lines[i] = f"{m.group(1)}. {fixed}"
                changed += 1
    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    return changed


def fix_canticle(canticle, only_canto):
    """Apply `fix_file` across a canticle's committed tags files. Returns (files_changed,
    labels_changed)."""
    cantos = cantos_for(canticle)
    if only_canto is not None:
        cantos = [c for c in cantos if c == only_canto]
    files, labels = 0, 0
    for canto in cantos:
        n = fix_file(out_path(TAGS_DIR, canticle, canto))
        if n:
            files += 1
            labels += n
            print(f"  fixed {n} label(s) in {canticle}/{canto:02d}.txt")
    return files, labels


def check_canticle(canticle, only_canto, tags_problems, reading_notes, elision_warnings):
    cantos = cantos_for(canticle)
    if only_canto is not None:
        cantos = [c for c in cantos if c == only_canto]
    if not cantos:
        print(f"  (no tags files for {canticle}"
              f"{f' canto {only_canto}' if only_canto else ''})")
        return 0

    scenes_checked = 0
    for canto in cantos:
        _, scenes = load_scenes(canticle, canto)
        reading = scene_bodies(out_path(READING_DIR, canticle, canto))
        tags = scene_bodies(out_path(TAGS_DIR, canticle, canto))
        markup_path = MARKUP_DIR / canticle / f"{canto:02d}.txt"
        lines = read_markup(canticle, canto) if markup_path.exists() else None

        for s, e, name in scenes:
            scenes_checked += 1
            where = f"{canticle} {canto:02d} scene {s}-{e}"
            k = markup_k(canticle, canto, lines, s, e)
            r_nums = reading_tag_numbers(reading.get((s, e), ""))
            t_res = tags_resolution(tags.get((s, e), ""))
            t_nums = set(t_res)

            # ---- COUNT check ----
            # Authoritative baseline: the deterministic markup count k (= {1..k}). tags is the
            # committed artifact, so a tags ≠ {1..k} is a STRUCTURAL defect; reading is free
            # prose, so a reading ≠ {1..k} is a COVERAGE note (the prose skipped/added a tag),
            # not a tags fault. They are reported separately.
            expected = set(range(1, k + 1)) if k is not None else (r_nums or t_nums)
            kdesc = f"k={k}" if k is not None else f"expected={sorted(expected)}"

            if t_nums != expected:
                bits = []
                if expected - t_nums:
                    bits.append(f"missing {sorted(expected - t_nums)}")
                if t_nums - expected:
                    bits.append(f"extra {sorted(t_nums - expected)}")
                tags_problems.append(
                    f"{where} [{name}]: tags resolve {len(t_nums)} of {kdesc} — "
                    + "; ".join(bits))

            if r_nums != expected:
                bits = []
                if expected - r_nums:
                    bits.append(f"omits {sorted(expected - r_nums)}")
                if r_nums - expected:
                    bits.append(f"adds {sorted(r_nums - expected)}")
                reading_notes.append(
                    f"{where} [{name}]: reading lists {len(r_nums)} of {kdesc} — "
                    + "; ".join(bits))

            # ---- ELISION check ----
            for n, label in t_res.items():
                for m in ELIDE_RE.finditer(label):
                    elision_warnings.append(
                        f"{where} [{name}]: tag {n} = '{label}' "
                        f"(\"{m.group(1)} {m.group(2)}\" — should it be elided?)"
                    )

    print(f"  {canticle}: {len(cantos)} canto(s), {scenes_checked} scene(s) checked")
    return scenes_checked


def main():
    parser = argparse.ArgumentParser(
        description="Verify 05-tags/ resolution tables: tag-count agreement (markup k / reading / "
                    "tags) and elision over-correction candidates. No LLM.")
    parser.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    parser.add_argument("-c", "--canto", type=int, help="Check only this canto.")
    parser.add_argument("--strict", action="store_true",
                        help="Also exit non-zero on reading-coverage or elision findings.")
    parser.add_argument("--fix", action="store_true",
                        help="Repair elision over-corrections in the committed 05-tags/ files in "
                             "place (then report the post-fix state).")
    args = parser.parse_args()

    if args.fix:
        print("Fixing elisions…")
        files, labels = 0, 0
        for canticle in args.canticles:
            f, l = fix_canticle(canticle, args.canto)
            files += f
            labels += l
        print(f"  {labels} label(s) re-elided across {files} file(s).\n"
              if labels else "  nothing to fix.\n")

    tags_problems, reading_notes, elision_warnings = [], [], []
    total = 0
    print("Checking…")
    for canticle in args.canticles:
        total += check_canticle(canticle, args.canto, tags_problems, reading_notes,
                                elision_warnings)

    # 1. tags vs the authoritative markup count — the structural guarantee.
    print()
    if tags_problems:
        print(f"TAGS COUNT — {len(tags_problems)} structural problem(s):", file=sys.stderr)
        for p in tags_problems:
            print(f"  - {p}", file=sys.stderr)
    else:
        print("TAGS COUNT: OK — every scene resolves exactly its {1..k} tags.")

    # 2. reading enumeration vs the same count — advisory (reading is free prose).
    print()
    if reading_notes:
        print(f"READING COVERAGE — {len(reading_notes)} scene(s) where the reading prose "
              f"enumerates a different tag set than 05-tags/ (05-tags/ is authoritative):")
        for nzote in reading_notes:
            print(f"  - {nzote}")
    else:
        print("READING COVERAGE: every reading enumerates the same tag set as 05-tags/.")

    # 3. elision over-correction candidates (PLAN.md known residual, next-stage fix).
    print()
    if elision_warnings:
        print(f"ELISION — {len(elision_warnings)} candidate(s) to review "
              f"(known residual, PLAN.md):")
        for w in elision_warnings:
            print(f"  - {w}")
    else:
        print("ELISION: none flagged.")

    print(f"\nDone: {total} scene(s); {len(tags_problems)} tags-count problem(s), "
          f"{len(reading_notes)} reading-coverage note(s), "
          f"{len(elision_warnings)} elision candidate(s).")
    if tags_problems or (args.strict and (reading_notes or elision_warnings)):
        sys.exit(1)


if __name__ == "__main__":
    main()
