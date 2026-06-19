#!/usr/bin/env python
"""
Lock conformance — the measurable PROOF that 14-lock keeps the digest from drifting (PLAN.md
direction 1). Pure code, no LLM.

For every scene, code builds the closed name vocabulary the scene's 14-lock entry licenses (cast
figures, speech parties, setting, soul-class, and the KG-resolved refer/relations/simile names) and
then checks the committed digest against it: every proper name the digest asserts for a scene must
appear in that scene's lock vocabulary. A name outside it is a DEVIATION — measurement data, not
something to hand-correct (README "Premise"; ARCHITECTURE "Keep the project measurable").

Coverage is asymmetric by language. English names are Title-cased, so a capitalized-token scan gives
a clean closed-set membership check (sentence-initial words and common English capitals are stopped).
Japanese keeps every name in SOURCE spelling, so any Latin-script run is a name surface; the same
membership check runs over those runs. Word-boundary ambiguity means Japanese out-of-lock detection
is weaker than English — treat the English rate as the primary proof.

Input:  15-digest/<canticle>/NN.txt   (committed digest — run digest.py first)
        14-lock/<canticle>/NN.toml    (committed lock — the licensed vocabulary)
Output: a per-canto conformance report (stdout): asserted names, in-lock, and the out-of-lock list.
"""
import argparse
import re
import sys

from dante_analyze import available_cantos, load_scenes, load_lock, load_digest, split_set

# A Latin-script word token (accented letters and internal apostrophes kept): the surface a name
# takes in BOTH languages, since the digest keeps every name in its source spelling.
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ']*")

# Common English words that are capitalized only because they open a sentence or a clause — never a
# Dante figure, so they are not deviations when they appear capitalized. (Sentence-initial position
# is also stopped; this catches mid-sentence capitals like `I`.)
STOPWORDS = {
    "The", "A", "An", "And", "But", "Or", "Nor", "So", "Yet", "For", "As", "When", "While", "Then",
    "Here", "There", "Now", "Thus", "He", "She", "They", "It", "We", "I", "His", "Her", "Their",
    "This", "That", "These", "Those", "Who", "Whom", "Where", "With", "In", "On", "At", "To", "Of",
    "By", "From", "After", "Before", "Though", "Although", "Because", "If", "Upon", "Once", "Soon",
    "Still", "Both", "One", "Two", "Each", "All", "No", "Not", "Their", "Its", "Our", "Your",
}


def _strip_possessive(word):
    """`Dante's` -> `Dante`: drop an English possessive so the name matches the lock surface."""
    return re.sub(r"'s$", "", word)


def licensed_words(lock_scene, all_whos):
    """The casefolded set of every WORD a scene's lock entry licenses — drawn from the FULL surface
    of each licensed name, epithet, setting, and soul-class (a lock epithet like `quei che con lena
    affannata` or `loco selvaggio` is carried into the digest verbatim, so every one of its words is
    licensed, lowercase included). The digest may surface any of these; a token outside the set is a
    deviation. `dante` is always licensed."""
    names = {"Dante"}
    for fig in lock_scene.get("cast", []):
        names.add(fig["who"])
        members = split_set(fig["who"], all_whos)
        if members:
            names.update(members)
    for sp in lock_scene.get("speech", []):
        for party in (sp.get("speaker"), sp.get("addressee")):
            if party and party not in ("(none)", "(unattributed)"):
                names.add(party)
    for key in ("refer", "relations", "simile"):
        for entry in lock_scene.get(key, []):
            for field in ("subj", "obj", "vehicle", "phrase", "resolves"):
                if field in entry:
                    names.add(entry[field])
    for field in ("location", "region"):
        if lock_scene.get(field):
            names.add(lock_scene[field])
    names.update(lock_scene.get("cohort", []))

    words = set()
    for name in names:
        for word in TOKEN_RE.findall(name):
            words.add(word.casefold())
    return words


def en_deviations(text, allowed):
    """Capitalized name tokens the English digest asserts that are NOT licensed by the scene's lock,
    skipping sentence-initial words and common-English capitals (STOPWORDS). Possessive `'s` is
    stripped before the membership test."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = TOKEN_RE.findall(sentence)
        for i, word in enumerate(words):
            if not word[:1].isupper() or word in STOPWORDS or i == 0:
                continue  # lowercase / common capital / sentence-initial: not a name assertion
            if _strip_possessive(word).casefold() not in allowed:
                out.append(word)
    return out


def ja_deviations(text, allowed):
    """Latin-script tokens the Japanese digest carries that are NOT licensed — names are kept in
    source spelling, so any Latin run is a name (or an epithet word) surface. A licensed lowercase
    Italian epithet carried verbatim passes; an UNTRANSLATED English fragment (e.g. `the suffering
    spirits`) does not — exactly the residual the measurement should surface."""
    return [w for w in TOKEN_RE.findall(text) if w.casefold() not in allowed]


def check_canto(canticle, canto):
    """(asserted, in_lock, deviations) for a canto, where `deviations` is a list of
    (scene, lang, token). Counts every flagged proper-name assertion across both languages."""
    _, scenes = load_scenes(canticle, canto)
    digest = load_digest(canticle, canto)
    locks = {tuple(int(x) for x in sc["lines"].split("-")): sc
             for sc in load_lock(canticle, canto)["scenes"]}
    all_whos = [fig["who"] for sc in locks.values() for fig in sc.get("cast", [])]

    asserted = in_lock = 0
    deviations = []
    for s, e, _name in scenes:
        body = digest.get((s, e))
        lock_scene = locks.get((s, e))
        if not body or lock_scene is None:
            continue
        allowed = licensed_words(lock_scene, all_whos)
        for lang, finder in (("en", en_deviations), ("ja", ja_deviations)):
            text = body.get(lang, "")
            # name-like assertions checked: capitalized non-initial tokens (en) / any Latin run (ja).
            if lang == "en":
                checked = sum(
                    1 for sent in re.split(r"(?<=[.!?])\s+", text.strip())
                    for i, w in enumerate(TOKEN_RE.findall(sent))
                    if w[:1].isupper() and w not in STOPWORDS and i != 0)
            else:
                checked = len(TOKEN_RE.findall(text))
            bad = finder(text, allowed)
            asserted += checked
            in_lock += max(checked - len(bad), 0)
            for tok in bad:
                deviations.append((f"{s}-{e}", lang, tok))
    return asserted, in_lock, deviations


def main():
    ap = argparse.ArgumentParser(
        description="Measure 14-lock conformance of the committed digest (the proof; see "
                    "15-digest/README.md).")
    ap.add_argument("canticles", nargs="+", help="Canticle name(s), e.g. inferno")
    ap.add_argument("-c", "--canto", type=int, help="Only this canto.")
    args = ap.parse_args()

    for canticle in args.canticles:
        cantos = available_cantos(canticle) if args.canto is None else [args.canto]
        t_asserted = t_in = 0
        for canto in cantos:
            try:
                asserted, in_lock, deviations = check_canto(canticle, canto)
            except SystemExit:
                continue  # a canto missing its committed digest/lock file: skip, keep going
            t_asserted += asserted
            t_in += in_lock
            rate = (in_lock / asserted * 100) if asserted else 100.0
            print(f"{canticle} {canto:02d}: {in_lock}/{asserted} in lock ({rate:.1f}%)"
                  f"{' — ' if deviations else ''}"
                  + ", ".join(f"{sc}/{lang}:{tok}" for sc, lang, tok in deviations))
        if t_asserted:
            print(f"\n{canticle} TOTAL: {t_in}/{t_asserted} in lock "
                  f"({t_in / t_asserted * 100:.1f}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
