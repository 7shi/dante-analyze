import argparse
import json
import sys
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from llm7shi.compat import generate_with_schema
import dante_corpus as dc

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent

# Canticle directory name -> English title used in the output heading.
CANTICLE_TITLES = {
    "inferno": "Inferno",
    "purgatorio": "Purgatorio",
    "paradiso": "Paradiso",
}

# Default target language for scene names / summaries. English keeps the local
# LLM close to the source reasoning and avoids translation overhead.
DEFAULT_LANGUAGE = "English"


class Scene(BaseModel):
    """A single scene within a canto."""
    start_line: int = Field(description="First line number of the scene (1-based).")
    end_line: int = Field(description="Last line number of the scene (1-based).")
    scene_name: str = Field(description="Short, concrete label for the dominant event of the passage.")
    summary: str = Field(description="Concise one-sentence summary of what happens in this range.")


class CantoBreakdown(BaseModel):
    """Scene breakdown for one canto."""
    canto_title: str = Field(description="Short title summarizing the canto as a whole.")
    scenes: list[Scene] = Field(description="Scenes in order, covering the canto from the first to the last line without gaps or overlaps.")


def write_file(path, content):
    Path(path).write_text(content, encoding="utf-8")


def build_planning_prompt(numbered, total_lines, language):
    """Turn 1: free-form reasoning about how to divide the canto into scenes."""
    return f"""You are an expert on Dante's Divina Commedia.

Below is the canto with line numbers (1 to {total_lines}):

```
{numbered.rstrip()}
```

Think through how best to divide this canto into scenes for a reading guide, and
write your reasoning as a plain reply (prose, not yet a final table).

## Guidelines
1. Divide at any natural shift in the text — a change of place, speaker, action, or topic.
2. Prefer FINE granularity: aim for roughly 10–18 lines per scene, and whenever a
   passage could be read as one scene or as several, always choose the finer split.
   Over-splitting is intended here: merging two adjacent scenes afterward is trivial,
   but splitting a scene later would require re-reading the source. So err strongly
   toward more, smaller scenes. A scene of only a couple of tercets (~6 lines) is fine,
   and you must NOT merge scenes just because one is short.
3. A canto of {total_lines} lines should yield roughly {max(2, round(total_lines / 15))} scenes or MORE; a dozen or
   more is perfectly fine. Do NOT reduce the count to make scenes feel larger.
4. The scenes together must cover every line from 1 to {total_lines} in order, with no
   gaps and no overlaps: the first scene starts at line 1, the last ends at line {total_lines},
   and each scene starts on the line right after the previous one ends.

For each scene you settle on, give its line range, a short concrete name for the
dominant event, and one sentence on what happens. Write in {language}."""


def build_structure_prompt(language, total_lines):
    """Turn 2: organize the reasoning above into the structured schema."""
    return f"""Now organize the scene division you just described into the final structured form.

- `canto_title`: a short title summarizing the whole canto.
- `scenes`: one entry per scene, each with `start_line`, `end_line`, `scene_name`, `summary`.
- Cover lines 1 to {total_lines} in order. Each `start_line` must be greater than the previous
  scene's, with no gaps, no overlaps, and no duplicated rows. Do NOT add a row spanning
  the whole canto.

Write `canto_title`, `scene_name`, and `summary` in {language}. Do not add anything else."""


def build_retry_prompt(problems, total_lines, language):
    """Turn 2 retry: tell the model exactly which range checks it failed."""
    issues = "\n".join(f"- {p}" for p in problems)
    return f"""The scene ranges you produced are invalid:
{issues}

Produce the structured output again, fixing these problems. The scenes must cover
every line from 1 to {total_lines} in order: the first scene starts at line 1, the last
ends at line {total_lines}, each scene's `start_line` is exactly the previous scene's
`end_line` + 1, and no range is reversed. Keep `canto_title`, `scene_name`, and
`summary` in {language}."""


def check_ranges(scenes, total):
    """Check one canto's scene ranges. Returns a list of problem strings (empty = OK).

    `total` is the source line count, or None to skip the coverage check.
    """
    if not scenes:
        return ["no scenes"]
    problems = []
    expected = 1  # next line that should be covered
    for i, s in enumerate(scenes, start=1):
        if s.end_line < s.start_line:
            problems.append(f"scene {i}: reversed range {s.start_line}-{s.end_line}")
        if s.start_line > expected:
            problems.append(f"lines {expected}-{s.start_line - 1} uncovered before scene {i}")
        elif s.start_line < expected:
            problems.append(f"scene {i}: overlaps previous (starts at {s.start_line}, expected {expected})")
        expected = max(expected, s.end_line + 1)
    covered_end = expected - 1
    if total is not None and covered_end != total:
        problems.append(f"scenes end at line {covered_end} but source has {total} lines")
    return problems


def format_canto(canto_num, breakdown):
    """Render a CantoBreakdown as a Markdown section with a scene table."""
    lines = [f"## Canto {canto_num}: {breakdown.canto_title}", ""]
    lines.append("| Lines | Scene | Summary |")
    lines.append("|---|---|---|")
    for scene in breakdown.scenes:
        rng = f"{scene.start_line}-{scene.end_line}"
        lines.append(f"| {rng} | {scene.scene_name} | {scene.summary} |")
    lines.append("")
    return "\n".join(lines)


def split_canto(canticle, canto_num, language, model, max_attempts=3):
    """Generate the scene breakdown for a single canto.

    Two-turn flow over a shared conversation:
    1. Free-form planning with chain-of-thought enabled: the model reasons in
       prose about where the scene boundaries fall.
    2. Structured output: the model turns that reasoning into a CantoBreakdown.
       The result is range-checked; on failure only Turn 2 is retried (with the
       specific problems fed back). After `max_attempts` consecutive failures the
       run aborts so no bad canto is written.
    """
    print(f"Splitting Canto {canto_num} ({canticle})...")
    canto_obj = dc.canto(canticle, canto_num)
    lines = canto_obj.lines()
    total = len(lines)
    numbered = "".join(f"{line.no} {line.text}\n" for line in lines)

    # Turn 1: free-form planning with chain-of-thought.
    planning_prompt = build_planning_prompt(numbered, total, language)
    planning = generate_with_schema(
        [planning_prompt],
        model=model,
        include_thoughts=True,
        show_params=False,
    )

    # Turn 2: structured output, reusing the planning reply (no CoT needed).
    messages = [
        {"role": "user", "content": planning_prompt},
        {"role": "assistant", "content": planning.text.strip()},
        {"role": "user", "content": build_structure_prompt(language, total)},
    ]
    for attempt in range(1, max_attempts + 1):
        response = generate_with_schema(
            messages,
            schema=CantoBreakdown,
            model=model,
            include_thoughts=False,
            show_params=False,
        )
        try:
            breakdown = CantoBreakdown.model_validate_json(response.text)
            problems = check_ranges(breakdown.scenes, total)
        except ValidationError as e:
            problems = [f"invalid structured output: {e}"]
        if not problems:
            return breakdown

        print(f"Canto {canto_num}: Turn 2 attempt {attempt}/{max_attempts} failed range check:",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        if attempt < max_attempts:
            # Retry Turn 2 only, feeding back the specific problems.
            messages = messages + [
                {"role": "assistant", "content": response.text.strip()},
                {"role": "user", "content": build_retry_prompt(problems, total, language)},
            ]

    print(f"Error: Canto {canto_num} failed the range check {max_attempts} times; aborting.",
          file=sys.stderr)
    sys.exit(1)


def json_path(canticle_dir, canto_num):
    """Per-canto JSON checkpoint path, e.g. inferno/01.json next to 01.txt."""
    return Path(canticle_dir) / f"{canto_num:02d}.json"


def load_breakdowns(canticle_dir):
    """Return {canto_num: breakdown_dict} from the per-canto JSON files present."""
    done = {}
    for p in Path(canticle_dir).glob("*.json"):
        done[int(p.stem)] = json.loads(p.read_text(encoding="utf-8"))
    return done


def write_json(path, breakdown):
    """Write one canto's breakdown to its per-canto JSON checkpoint (indent=2)."""
    Path(path).write_text(
        json.dumps(breakdown.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_markdown(title, breakdowns, output_path):
    """Render {canto_num: CantoBreakdown} to the final Markdown file.

    Ranges are already validated per canto in Turn 2 (see split_canto), so no
    further checking is done here."""
    sections = [f"# {title} scene breakdown", ""]
    for canto_num in sorted(breakdowns):
        sections.append(format_canto(canto_num, breakdowns[canto_num]))
    write_file(output_path, "\n".join(sections) + "\n")
    print(f"Scene breakdown written to {output_path}")


def cmd_split(canticle_dir, output_path, language, model, only_canto=None):
    canticle_dir = Path(canticle_dir)
    canticle_name = canticle_dir.name
    title = CANTICLE_TITLES.get(canticle_name, canticle_name.capitalize())

    all_cantos = dc.cantos(canticle_name)
    if not all_cantos:
        print(f"Error: No cantos found in {canticle_name}", file=sys.stderr)
        sys.exit(1)
    if only_canto is not None:
        if only_canto not in all_cantos:
            print(f"Error: Canto {only_canto} not found in {canticle_name}", file=sys.stderr)
            sys.exit(1)
        canto_nums = [only_canto]
    else:
        canto_nums = list(all_cantos)

    generated = {}
    for canto_num in canto_nums:
        jp = json_path(canticle_dir, canto_num)
        if only_canto is None and jp.exists():
            print(f"Canto {canto_num} already in {jp}, skipping.")
            continue
        breakdown = split_canto(canticle_name, canto_num, language, model)
        generated[canto_num] = breakdown
        write_json(jp, breakdown)

    # Render Markdown: the single canto in test mode, otherwise every canto with
    # a per-canto JSON in the directory.
    if only_canto is not None:
        breakdowns = {only_canto: generated[only_canto]}
    else:
        breakdowns = {n: CantoBreakdown.model_validate(b)
                      for n, b in load_breakdowns(canticle_dir).items()}
    write_markdown(title, breakdowns, output_path)


def main():
    default_model = "ollama:gemma4:26b"
    parser = argparse.ArgumentParser(
        description="Generate scene breakdowns for Dante's Divina Commedia (see ref/ for examples)."
    )
    parser.add_argument("inputs", nargs="+", help="Canticle directory/directories (e.g. inferno)")
    out_group = parser.add_mutually_exclusive_group(required=True)
    out_group.add_argument("-o", "--output", help="Output Markdown file (single directory only)")
    out_group.add_argument("--outdir", help="Output directory (file named <canticle>.md)")
    parser.add_argument("-m", "--model", default=default_model,
                        help=f"LLM model to use (default: {default_model})")
    parser.add_argument("-l", "--language", default=DEFAULT_LANGUAGE,
                        help=f"Language for scene names and summaries (default: {DEFAULT_LANGUAGE})")
    parser.add_argument("-c", "--canto", type=int,
                        help="Process only this canto number (for testing)")
    args = parser.parse_args()

    if args.output and len(args.inputs) > 1:
        print("Error: -o/--output can only be used with a single input directory. Use --outdir for multiple.",
              file=sys.stderr)
        sys.exit(1)

    for canticle_dir in args.inputs:
        if args.outdir:
            output_path = Path(args.outdir) / f"{Path(canticle_dir).name}.md"
        else:
            output_path = args.output

        cmd_split(canticle_dir, output_path, args.language, args.model, args.canto)


if __name__ == "__main__":
    main()
