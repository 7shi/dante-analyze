# Context lock (TOML) — plan (parked here; detailed design later, analyze-side)

This file holds the **context-lock TOML** spec and production plan, moved out of the translation
project (`dante-dravidian/it/PLAN.md` §3) because the lock **is referent resolution** — the
analysis layer's responsibility, not translation's.

> **Status:** parked. This is the spec as it stood in the translation plan, lifted here verbatim
> so it is not mixed into the main [`../PLAN.md`](../PLAN.md). The real integration with this
> repo's resolved data (`tags/` + the Active-work-1 speaker/edge join) is to be worked out later,
> on the analyze side. The hand-written reference sample lives beside this file:
> [`inferno-01.toml`](inferno-01.toml).

## What the lock is

A per-scene **context lock**: an identity-only record — who speaks, where we are, who "this light"
is — produced as **pre-processing for the dante-dravidian translation layer** ("Step 0"). It fixes
**identity only**, never the source's meaning or a paraphrase; each entry carries a `basis`
source quote so it is verifiable. It defends against the translation traps the layer is
designed to guard against.

## Fields (per scene)

| Field | Required | Defends against (translation trap) |
|---|---|---|
| `lines` | ✓ | anchor |
| `location` | ✓ | realm / topography slips |
| `cohort` | optional | wrong class of souls |
| `cast` | ✓ | character roster, creature/agent identity, garbled names, first-appearance / cross-canticle bleed |
| `speaker`, `addressee` | when spoken | speaker misidentification |
| `flags` (e.g. `misnames-addressee`) | optional | dramatic irony (a speaker mis-naming the addressee) |
| `refer` (`phrase` → `resolves`, with `note`) | optional | deixis / periphrasis; self vs. third party; reference-point-as-subject |
| `relations` (`who`/`role`/`of`) | optional | kinship / role errors |
| `simile` (`vehicle`, with `note`) | optional | simile vehicle mistaken for a character |
| `basis` | ✓ | verification |

## Format and layout

- **TOML**, one file per canto (e.g. `inferno/01.toml`), keyed to the canto so the source (served
  by dante-corpus), the per-canto scene breakdown (dante-corpus JSON `it/<canticle>/NN.json`), and
  the lock form a consistent per-canto bundle, one-to-one.
- Scenes are an array of tables (`[[scene]]`); `refer` and `simile` are arrays of inline tables,
  which stay readable and hand-editable.

## Production (sketch — to be reconciled with this repo's resolved data)

1. Most lock fields should be **derivable from the resolved data** this repo already produces:
   `speaker`/`addressee`/`cast` from `tags/` + the quote-span × tag join (Active work 1 in
   [`../PLAN.md`](../PLAN.md)); `refer` from the reading's Tag Resolutions.
2. For fields the join can't fill, a focused extraction prompt asks only for the lock fields
   ("identify the speaker, addressee, location, cast, referents, and similes for these lines") — a
   narrow task far more reliable than doing it implicitly while translating.
3. Drafts are checked against the source (the `basis` quotes make this fast); the verified lock
   feeds the translation pipeline as its **Step 0**.

## Reference sample

[`inferno-01.toml`](inferno-01.toml) is a hand-written full lock for Inferno Canto 1 (20 scenes,
contiguous over lines 1–136), kept to compare a model-/join-derived version against. It shows the
skeleton catching real traps — e.g. resolving "figliuol d'Anchise" → **Aeneas** (the
Anchises-confusion that hit Paradiso 15), and marking the swimmer and miser similes as imagery
rather than characters.

## Open question — name form in the lock

The `speaker`/`addressee`/`cast` data comes from this repo's `tags/` (+ the `quotes/ref` speaker
sample) in **source spelling** (`Virgilio`, `Frati Godenti`) — the deliberate policy here
(translation is needless overhead for the local LLM). The reference sample and an eventual
translation glossary instead use anglicized forms (`Virgil`, `Cassio → Cassius`). Reconcile:
either the lock adopts source spelling to match the tags (likely preferred, same rationale), or
define a single normalization point. Deferred — agreement is currently on *who* speaks, not the
exact string.
