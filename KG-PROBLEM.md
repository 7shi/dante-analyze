# The identification gap in the KG ladder

> **Status — parked until the active `PLAN.md` work settles.** This is a known limitation to
> revisit *after* the translation context lock (the active direction in `PLAN.md`, passes `09`–`14`)
> is complete — not a blocker for it. The KG ladder (`01`–`08`) is committed and usable today, and
> the context lock does not depend on closing this gap. The gap degrades the character count and
> minor-figure queries (see "Impact" below); the fixes belong to a later cleanup pass on the
> registry, taken up once the lock passes land.

## What the KG is for

Two requirements drive the knowledge graph:

1. **Accurate character listing** — one node per actual figure, no duplicates, no phantom entries.
   The graph should report how many characters appear in the Comedy and who they are.
2. **Person-centric dynamics extraction** — querying a figure ("what does Virgil do?", "who
   interacts with Ulysses?") returns *all* of that figure's edges, with nothing silently missing.

Both depend entirely on **node identity**: if the same person is split across two nodes, the
listing over-counts and the query misses edges. This document describes the structural gap that
prevents the current pipeline from meeting these requirements, and what would be needed to close
it.

> **Key structural fact.** Steps `06`–`08` (speech, relations, assembly) all join to the registry
> by `fold_key → node`. Once the node set is correct, the downstream pipeline produces the correct
> graph automatically — no re-extraction of edges or speech is needed. **The fix is concentrated
> in node construction.**

---

## What "identification" means here

**Cross-tag coreference**: determining that two tags in different scenes refer to the *same figure*,
so their edges connect to one node. This is distinct from **per-tag resolution** (what a single
surface form refers to), which `04-tags` already does.

`04-tags` resolves each mark (`[tu]`, `{Virgilio}`, `'l mio maestro`) to a figure name based on the
reading — one `n. Name` line per tag. It does NOT cross-link tags: it never says "tag [1] in scene A
and tag [3] in scene B are the same figure." Within a scene it aims for label consistency ("use the
SAME label for every tag referring to it in this scene"), but across scenes the labels drift.

The registry's `fold_key` handles only the cosmetic drift (case-fold + leading-article strip). The
epithet grouping — the step that would merge genuinely different labels for the same figure — was
sized by `measure.py`, failed both decision gates, and was skipped in v1. **There is no coreference
resolution step in the pipeline.**

| Step | What it does | Cross-tag coreference? |
|------|-------------|----------------------|
| `04-tags` | Resolves each tag to a figure name, per scene, from the reading | No — each tag named independently |
| `05-registry` fold_key | Merges case/article variants (`il Navarrese`/`Navarrese`) | Cosmetic only — 149 groups, 360 labels |
| `05-registry` epithet grouping | Would merge semantic variants (different words, same figure) | **Skipped** (gates failed) |
| `08-kg` | Assembles the graph from registry nodes | Inherits fragmentation |

---

## Evidence: the registry counts labels, not figures

### Node count vs. reality

The registry has **1,026 nodes typed `individual`**. The Divine Comedy has roughly 300–500 named
historical, biblical, and mythological figures — an over-count of **~2×**.

### Type distribution (all typed nodes)

| Type | Count | Share |
|------|------:|------:|
| individual | 1,026 | 40% |
| class | 681 | 27% |
| non-person | 517 | 20% |
| generic | 292 | 11% |
| hypothetical-simile | 38 | 1% |
| **total** | **2,554** | |

### Where the phantom individuals come from

**(a) Same figure, different labels (fragmentation).** First-token analysis (case-folded first word)
reveals **48 name clusters** — a capitalized first token shared by more than one individual node
(80 first-token clusters in all, counting the lowercase demonstrative/descriptive heads of (c)):

| Token | Nodes | Example labels |
|-------|------:|----------------|
| `Guido` | 10 | `Guido da Montefeltro` (20), bare `Guido` (12), `Guido Guerra` (5), `Guido Cavalcanti` (1), … |
| `Pier` | 7 | `Pier della Vigna` (26), `Pier delle Vigne` (1) — **spelling variant**, `Pier da Medicina` (11), … |
| `Pietro` | 6 | `Pietro` (12), `Pietro Damiano` (6), `Pietro Damian` (1) — **spelling variant**, … |
| `Dio` | 5 | `Dio` (270), `Dio Padre` (4), `Dio Figlio` (1), `Dio Spirito Santo` (1) |
| `Guiglielmo` | 4 | `Guiglielmo Borsiere` (4), `Guiglielmo marchese` (4), `Guiglielmo Aldobrandesco` (3), bare `Guiglielmo` (6) |
| `Francesco` | 3 | `Francesco d'Accorso` (1), `Francesco` (34), `Francesco d'Assisi` (7) |

Some clusters mix **different people sharing a first name** (`Guido da Montefeltro` ≠ `Guido Guerra`
≠ `Guido Cavalcanti` — resolving these requires scene context). But others contain **the same person
under different labels or spellings** (`Pier della Vigna` = `Pier delle Vigne`; `Pietro Damiano` =
`Pietro Damian`). `fold_key` cannot merge either case because the content tokens differ.

**(b) Singletons — 474 of 1,026 individuals (46%) appear exactly once.** Many are one-off
periphrastic descriptions that `04-tags` emitted because the reading described the figure without
naming it (`colui che sì presso ha 'l riprezzo de la quartana`, `la persona con cui il Navarrese
fece mala partita`). Each unique description becomes its own node; if the same figure appears in
another scene under a different description, another node is created.

**(c) Demonstrative/descriptive labels counted as individuals.** Context-specific references that
point to **different figures in different scenes** inflate the individual count:

| Token | Nodes | Examples |
|-------|------:|---------|
| `quel` | 25 | `quel cane`, `quel grande`, `quel caduto`, `quel da Esti`, … |
| `colui` | 11 | `colui che va giuso`, `colui che 'l mondo schiara`, … |
| `quella` | 6 | `quella compagna`, `quella viva luce`, … |

These are referential expressions, not figure names. Each scene's `quel X` is a different person;
they should not be individual nodes at all.

---

## Why epithet grouping was skipped

`measure.py` produced two decision gates; both failed:

| Gate | Threshold | Measured | Result |
|------|-----------|----------|--------|
| base figures with longer forms | < 50 | 346 | FAIL |
| epithet nodes/canticle | < 150 | 285–330 | FAIL |

The 1,010 near-dupe pairs (content-token subset: `Adamo` ⊂ `Maestro Adamo`) are a fuzzy signal, not
missed identifications. Of 333 content-sharing individual pairs examined, **the true-positive rate
is under ~6%** — most are genuinely different figures sharing a common word:

- `Guido` ⊂ `Guido Guinizzelli` and `Guido` ⊂ `Guido da Montefeltro` — **different people**.
- `Dio` ⊂ `dio d'oro e d'argento` — an idol, **not God**.
- `il Padre` ⊂ `il padre di Cavalcante della Scala` — Cavalcante's father, **not God the Father**.

v1 ships **Option A**: epithet grouping skipped, every non-cap-name non-set node flagged
`grouped: no`. The rationale: a flagged singleton is safer than a merge the structural check cannot
verify. Wrong merges (two different figures collapsed into one node) silently corrupt every
downstream edge; missed merges (one figure as two nodes) only reduce connectivity.

---

## Impact on the KG

### Requirement 1 — accurate character listing

The KG has **~2× too many individual nodes** (1,026 vs an expected 300–500). The listing is
inflated by fragmentation (same figure, multiple nodes), singletons (one-off descriptions counted
as individuals), and demonstrative labels (`quel`, `colui` — different people in each scene). No
downstream filter can remove these phantom nodes; they must be resolved at node-construction time.

### Requirement 2 — person-centric dynamics extraction

- **Major figures** (Dante, Virgil, Beatrice, and other consistently named figures) are
  **reliable**. `04-tags` resolves them by proper name throughout, so they are one node each and
  their edges connect correctly. Querying "what does Virgilio do?" returns the right answer.
- **Mid-tier and minor figures** are **unreliable**. A figure split across bare `Guido` (12) and
  `Guido da Montefeltro` (20) means querying either node returns a partial view. The user cannot
  tell which nodes are complete and which are fragments without inspecting each one.

---

## What is needed

A **coreference resolution** step between `04-tags` and typing — one that sees all labels with
their scene context and groups same-figure mentions. The data suggests three tractable
sub-problems, in order of increasing difficulty:

### 1. Curate a deterministic merge table (low effort, high precision)

The genuine same-figure splits — where two nodes are unambiguously the same person — are few
(~10–20 pairs):

- `Latino` (9) = `Brunetto Latino` (28) = `Ser Brunetto Latino` (5)
- `Maestro Adamo` (30) = `Mastro Adamo` (10)
- `Pier della Vigna` (26) = `Pier delle Vigne` (1)
- `San Pietro` (35) = `Pietro` (12)
- `Cristo` (96) = `Iesù Cristo` (3)

A hand-maintained alias table in `05-registry` would collapse these deterministically, with full
verifiability (each merge is a curated fact, not an LLM judgment).

### 2. Context-aware LLM coreference (the real fix, hardest)

For the residual — bare first names (`Guido`, `Arrigo`, `Francesco`), generic epithets
(`l'angelo`, `la madre`, `poeta`) — each candidate must be presented with its **scene context**
(the reading) so the model can judge which existing node it refers to. This is the epithet grouping
the gate said was too big for one call per canticle. It may be tractable in smaller batches with
context, but:

- The result **cannot be structurally verified** (a wrong merge passes the check).
- **False positives dominate**: most name-sharing pairs are different people.
- The merge must be **per-tag, not per-label**: "this `Guido` in scene X is Guido da Montefeltro,
  but that `Guido` in scene Y is Guido Guerra."

This step, if attempted, should come **after** fix 1 (merge table), which reduces the candidate
pool and removes the clear-cut cases.
