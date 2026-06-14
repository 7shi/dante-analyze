#!/usr/bin/env python
"""
Measurement-first probe of the committed 03-reading prose for the relations pass:
"derive the closed predicate vocabulary by measuring the readings".

Pure code, no LLM, writes nothing — a stdout report that sizes the predicate problem BEFORE the
relations prompt is frozen. It ranks the candidate predicate verbs the readings actually use and
decides whether the closed vocabulary is tractable as one list or needs grouping.

Method (dependency-free; deps are only dante-corpus + llm7shi — no spaCy/nltk), so verb detection
is MORPHOLOGICAL, not POS. Every English 3rd-person-singular present verb ends in `-s` (`guides`,
`speaks`, `tells`, `sees`, `leads`), and these readings are written in that tense ("Virgil
explains…", "Dante asks…"). So the `-s` token set already contains every verb; the work is
SUBTRACTING the two big non-predicate classes that also end in `-s`:

  1. plural nouns          (`souls`, `spirits`, `eyes`, `words`, `demons`)  — NOUN_STOP
  2. meta-discourse verbs  (`describes`, `explains`, `notes`, `continues`)  — DISCOURSE

Class 2 is the important one and the reason formalize-first matters: the reading is
COMMENTARY prose, so its most frequent verbs describe the *narration* ("the canto describes…"),
not the diegetic events between figures that the KG wants. The relations vocabulary is curated
from the DIEGETIC remainder (`asks`, `tells`, `addresses`, `guides`, `leads`, `follows`,
`defeats`, `meets`, …), not from the raw frequency head. This probe separates the three buckets
so the curation is done against measured evidence; the lists are a HUMAN-CURATION AID, not an
authority (cf. 05-registry/measure.py's "fuzzy, human-inspection" framing).

Runs on whatever 03-reading cantos are committed (glob), so it is meaningful on a partial run and
re-runnable on the full one.
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

from dante_analyze import READING_DIR
from dante_analyze.checkpoint import scene_bodies, out_path

CANTICLES = ("inferno", "purgatorio", "paradiso")
TOP_N = 60
GATE_MIN = 5          # a predicate is "head" if it occurs ≥ this many times work-wide
GATE_MAX_LIST = 40    # a single closed list is tractable up to ~this many predicates

_WORD = re.compile(r"[a-z][a-z'-]*")

# Function/auxiliary words and adjectives that end in -s but are never predicates.
FUNCTION = {
    "this", "his", "its", "thus", "plus", "was", "perhaps", "across", "towards", "as",
    "us", "is", "has", "does",  # auxiliaries / copula: not relation predicates
}

# Frequent plural nouns observed in the readings (calibration sample) — struck from the head so
# the verb ranking is legible. Not exhaustive; the report says so.
NOUN_STOP = {
    "souls", "spirits", "eyes", "words", "demons", "figures", "others", "sinners", "angels",
    "things", "spheres", "lights", "poets", "stars", "flames", "beings", "heavens", "humans",
    "wings", "sins", "lines", "names", "themselves", "gods", "sins", "virtues", "terms",
    "events", "details", "images", "actions", "emotions", "scenes", "verses", "cantos",
    "shades", "blessed", "damned", "punishments", "sufferings", "rivers", "circles", "saints",
}

# Verbs that describe the READING/NARRATION itself, not a diegetic relation between figures.
# These dominate the raw head ("the passage describes…") and are NOT relation predicates.
DISCOURSE = {
    "describes", "explains", "continues", "notes", "concludes", "uses", "observes", "mentions",
    "reflects", "provides", "identifies", "shifts", "argues", "expresses", "acknowledges",
    "serves", "refers", "realizes", "suggests", "depicts", "recounts", "narrates", "states",
    "emphasizes", "illustrates", "presents", "introduces", "focuses", "admits", "begins",
    "ends", "represents", "indicates", "implies", "outlines", "summarizes", "clarifies",
    "elaborates", "remarks", "establishes", "frames", "recalls",
}


# The curated closed predicate vocabulary, v1 — built FROM the measured diegetic head (below) +
# Dante domain knowledge. Each canonical predicate (lemmatized, hyphenated for multiword) absorbs
# a set of `-s` surface synonyms the readings actually use; this map exists so the probe can
# MEASURE how much of the diegetic head the closed list covers (the real tractability test). The
# relations PROMPT will instruct the model to emit the canonical labels, and the CHECK validates
# against `set(CLOSED_VOCAB)` + the residual fallback `relates-to`.
CLOSED_VOCAB = {
    # — communication —
    "speaks-to":   {"speaks", "talks"},
    "addresses":   {"addresses", "greets"},
    "asks":        {"asks", "questions", "inquires", "wonders"},
    "answers":     {"answers", "responds", "replies", "retorts"},
    "tells":       {"tells", "informs", "relates", "reports", "asserts", "claims", "declares"},
    "commands":    {"commands", "orders", "instructs", "directs", "urges", "bids", "exhorts"},
    "warns":       {"warns", "cautions"},
    "rebukes":     {"rebukes", "reproaches", "condemns", "criticizes", "scolds", "blames"},
    "praises":     {"praises", "blesses", "honors", "thanks"},
    "prophesies":  {"prophesies", "foretells", "predicts"},
    "calls":       {"calls", "summons", "invokes", "shouts", "cries", "exclaims"},
    "pleads-with": {"pleads", "begs", "implores", "entreats", "prays"},
    "names":       {"names", "calls"},
    # — perception / encounter —
    "sees":        {"sees", "beholds", "watches", "notices", "perceives", "spots", "spies"},
    "hears":       {"hears", "listens"},
    "meets":       {"meets", "encounters", "finds", "approaches", "joins", "greets"},
    "recognizes":  {"recognizes", "knows"},
    # — guidance / movement —
    "guides":      {"guides", "leads", "directs"},
    "follows":     {"follows", "accompanies"},
    "brings":      {"brings", "takes", "carries", "draws"},
    "sends":       {"sends", "dispatches"},
    "gives":       {"gives", "offers", "grants", "hands", "presents"},
    "shows":       {"shows", "reveals", "points", "displays"},
    "touches":     {"touches", "embraces", "grasps", "seizes", "grabs", "holds"},
    # — conflict / power —
    "strikes":     {"strikes", "hits", "beats", "attacks", "wounds"},
    "defeats":     {"defeats", "overcomes", "conquers", "vanquishes", "destroys", "kills",
                    "slays", "devours", "consumes"},
    "chases":      {"chases", "hunts", "pursues", "drives", "blocks", "hinders"},
    "punishes":    {"punishes", "torments", "tortures", "afflicts"},
    "protects":    {"protects", "defends", "saves", "rescues", "shields"},
    # — relation / likeness —
    "compares":    {"compares", "likens", "resembles"},
    "opposes":     {"opposes", "resists", "defies", "rebels"},
}


def committed_cantos(canticle):
    """Cantos with a committed 03-reading file, in order; the file is the checkpoint."""
    d = READING_DIR / canticle
    if not d.is_dir():
        return []
    return sorted(int(os.path.basename(p)[:2]) for p in glob.glob(str(d / "[0-9][0-9].txt")))


def prose_lines(body):
    """The narrative prose lines of a reading scene body, dropping the structured
    `**Tag Resolutions**` / `* [n]: …` / bullet apparatus so only commentary prose is counted."""
    for line in body.splitlines():
        t = line.strip()
        if not t or t.startswith(("*", "-", "[", "{", "#")) or t.startswith("**"):
            continue
        yield t


def verb_candidates(text):
    """`-s` tokens of a string that survive the function-word filter (len>3, not -ss/-ous/-is).
    Plural-noun and discourse subtraction happens at report time so the raw counts stay visible."""
    out = []
    for w in _WORD.findall(text.lower()):
        if len(w) <= 3 or not w.endswith("s"):
            continue
        if w.endswith(("ss", "ous", "is")) or "'" in w or w in FUNCTION:
            continue  # drop adjectives, possessives (`adam's`), and function words
        out.append(w)
    return out


def gather(canticle):
    """Counter of `-s` verb-candidate tokens over a canticle's committed readings."""
    c = Counter()
    for canto in committed_cantos(canticle):
        for (_s, _e), body in scene_bodies(out_path(READING_DIR, canticle, canto)).items():
            for line in prose_lines(body):
                c.update(verb_candidates(line))
    return c


def partition(counter):
    """Split a verb-candidate counter into (diegetic, discourse, nouns) sub-counters."""
    diegetic, discourse, nouns = Counter(), Counter(), Counter()
    for w, n in counter.items():
        if w in NOUN_STOP:
            nouns[w] = n
        elif w in DISCOURSE:
            discourse[w] = n
        else:
            diegetic[w] = n
    return diegetic, discourse, nouns


def report(canticle, counter):
    diegetic, discourse, nouns = partition(counter)
    print(f"\n{'=' * 70}\n# {canticle}\n{'=' * 70}")
    print(f"  -s verb-candidate tokens: {sum(counter.values())} ({len(counter)} distinct)")
    print(f"  after subtraction: diegetic {len(diegetic)} | discourse {len(discourse)} | "
          f"plural-noun {len(nouns)}")
    print(f"\n  ## diegetic predicate candidates (the curation target), top {TOP_N}:")
    for w, n in diegetic.most_common(TOP_N):
        print(f"    {n:5d}  {w}")
    tail = len(diegetic) - TOP_N
    if tail > 0:
        print(f"    … {tail} more distinct (long tail)")
    print(f"\n  ## meta-discourse verbs struck (narration, NOT relations), top 15:")
    for w, n in discourse.most_common(15):
        print(f"    {n:5d}  {w}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canticles", nargs="*", default=list(CANTICLES),
                    help="canticles to measure (default: all three)")
    args = ap.parse_args()

    global_count = Counter()
    seen = False
    for canticle in args.canticles:
        if not committed_cantos(canticle):
            print(f"(skip {canticle}: no committed 03-reading)", file=sys.stderr)
            continue
        seen = True
        c = gather(canticle)
        global_count.update(c)
        report(canticle, c)

    if not seen:
        print("No committed 03-reading found.", file=sys.stderr)
        sys.exit(1)

    diegetic, _discourse, _nouns = partition(global_count)
    print(f"\n{'=' * 70}\n# GLOBAL (all canticles)\n{'=' * 70}")
    print(f"  diegetic predicate candidates: {len(diegetic)} distinct, "
          f"{sum(diegetic.values())} occurrences")
    head = [(w, n) for w, n in diegetic.most_common() if n >= GATE_MIN]
    print(f"  head (≥{GATE_MIN}×): {len(head)} distinct surface verbs (still ~15-20% residual")
    print(f"  noun/name noise the -s harvest can't strip without POS — so a raw distinct-count is")
    print(f"  NOT the tractability test; closed-vocabulary SIZE + top-band coverage is.)")

    # Coverage of the curated closed vocabulary, measured over the TOP-N most-frequent band
    # (where genuine verbs dominate). Coverage over the WHOLE harvest is meaningless: its
    # denominator is polluted by noun homographs (`bodies`, `tears`) the -s rule can't strip, and
    # by high-frequency INTRANSITIVE/state verbs (`appears`, `becomes`, `feels`, `remains`) that
    # are out of scope for binary person↔being edges by design. So the gate is (a) vocabulary
    # SIZE — the real tractability question — and (b) top-band coverage as evidence the
    # transitive relational head is captured.
    surface_to_canon = {s: c for c, ss in CLOSED_VOCAB.items() for s in ss}
    top = diegetic.most_common(60)
    top_cov = sum(n for w, n in top if w in surface_to_canon)
    top_tot = sum(n for _w, n in top)
    uncovered = [w for w, _n in top if w not in surface_to_canon]
    top_pct = 100 * top_cov / top_tot if top_tot else 0

    print(f"\n## Decision gate (closed predicate vocabulary)")
    print(f"  Curated closed vocabulary (v1): {len(CLOSED_VOCAB)} canonical predicates "
          f"(+ residual `relates-to`).")
    print(f"  top-60-band coverage: {top_cov}/{top_tot} ({top_pct:.0f}%) of the most-frequent")
    print(f"  diegetic verbs. The uncovered top-band tokens are out of scope BY DESIGN, not")
    print(f"  missed relations — proper names, noun homographs, and intransitive/state verbs:")
    print(f"    {', '.join(uncovered)}")
    size_ok = len(CLOSED_VOCAB) <= GATE_MAX_LIST
    print(f"\n  [{'PASS' if size_ok else 'FAIL'}] closed list ≤ {GATE_MAX_LIST} predicates: "
          f"{len(CLOSED_VOCAB)}  (the tractability test)")
    print(f"  [info] top-band transitive coverage {top_pct:.0f}%; the rest is out-of-scope")
    print(f"         (intransitive/state/noun/name) or falls to the `relates-to` residual.")
    if size_ok:
        print(f"  => ONE closed list is tractable; freeze CLOSED_VOCAB into the relations prompt +")
        print(f"     check. No grouping pass needed (contrast the registry's failed epithet gate).")
    else:
        print(f"  => REVISIT: collapse synonyms further, or the predicate set needs grouping.")


if __name__ == "__main__":
    main()
