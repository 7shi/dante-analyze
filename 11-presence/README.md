# 11-presence — present cast vs merely-mentioned (context-lock Step 3)

The person analogue of the current-setting vs referred-to-place split `09-location` / `10-topography`
made for places. The action-only KG (`08-kg`) records who-does-what but does **not** mark who is
*bodily present* in a scene versus who is only *named* (talked about, recalled, foretold, invoked, or
used in a simile). The lock must preserve exactly that distinction (`../PLAN.md` "present cast versus
merely-mentioned referents"); this pass supplies it as its own single text-derived LLM judgment — one
judgment per script, so judgments never contaminate each other.

## How it works — closed-set classification, not free extraction

A scene's figures are **already resolved upstream**, so code gathers the roster and the LLM only
*labels* each figure `present` / `mentioned`. This is the `05-registry` node-typing structure applied
per scene, and it buys a strong structural check (every roster figure labeled exactly once, no figure
outside the roster) instead of re-extracting identities the pipeline has already fixed.

1. **Roster (code).** `scene_roster` takes the scene's `04-tags` labels, canonicalizes each through
   `raw_to_canonical` (`fold_key(norm_label(...))`, the same join `08-kg` uses), and keeps person-like
   registry types (`individual` / `generic` / `class`); a `set` node is expanded to its members.
   `non-person` (la Fortuna), `hypothetical-simile` (the swimmer, the miser), and `deictic`
   (scene-local `quel cane`, a different figure each scene) are **dropped** — similes are a separate
   code-join in the lock. Unresolved labels (`(unknown)` / un-registered) are
   tallied, not fatal. The roster is the closed set the LLM must classify, in first-mention order.
2. **Classify (LLM, one turn per scene).** The numbered scene source plus the roster list; the model
   labels each figure `present` (bodily on stage — acting, listening, addressed) or `mentioned` (named
   but not physically there), with a `basis` line range. CoT is **on** by default (`--no-think`
   disables): the reasoning runs in Ollama's thinking channel, `resp.text` is the label lines,
   `call_llm` caps runaway. Examples are schematic (the FORM only) — never a figure from the scene
   under test, so no answer leaks in.
3. **Check (code), retried in-conversation** (max 3 attempts, last draft kept flagged):
   - **closed-set (fatal):** every roster figure labeled exactly once (matched by `fold_key`, so a
     cosmetic spelling drift is tolerated and rendered back to the canonical roster label); no figure
     outside the roster; `status ∈ {present, mentioned}`.
   - **basis geometry (fatal):** each `basis` range lies within the scene `s..e`.
   - **present-anchor (soft, warning):** a scene speaker (`06-speech`) or `literal`-frame action
     subject (`08-kg`) — present by definition — labeled `mentioned` is flagged to stderr and kept;
     `reported` / `prophecy` frame subjects can legitimately be absent, so this is not fatal.

   Whether a `present` / `mentioned` call is *correct* is interpretation, shipped as generated — no
   hand-proofreading (improve the method and re-measure instead). A scene that names no person figure
   writes the `# (no person figure named in this scene)` marker.

## Inputs / outputs

```
Input:  02-markup/<canticle>/NN.txt   (source lines), 01-scenes JSON (load_scenes),
        04-tags + 05-registry         (the roster), 06-speech + 08-kg (soft present-anchors)
Output: 11-presence/<canticle>/NN.txt — per scene a `## Scene s-e: name` block of presence lines
        (the file is the checkpoint: a finished scene is skipped on resume; delete to regenerate)
```

### Scene block

```
## Scene 61-66: A Shadow in the Desert
- who: Dante | status: present | basis: 61-66
- who: Virgilio | status: present | basis: 62-63
- who: Beatrice | status: mentioned | basis: 64-64
```

- `who` — the canonical node label (source spelling, matching the KG nodes; per the `../PLAN.md`
  name-form rule);
- `status` — `present` | `mentioned`;
- `basis` — the source line range within the scene supporting the call (a line reference, so the full
  quote is recoverable at lock-assembly time, `14-lock` — the checkable core is not a fragile string).

Read downstream with `load_presence(canticle, canto)` → `{(s,e): [{who, status, basis_start,
basis_end}, …]}` (in `dante_analyze.checkpoint`, beside `load_locations`).

## Run

```bash
uv run 11-presence/presence.py inferno [-c 1] [-m MODEL] [--no-think]
make -C 11-presence        # all three canticles (sequential)
```

Model: `ollama:gemma4:31b-it-qat` by default (the stronger reader); the build was produced with a
Gemma-4-31B cloud endpoint (`-m`). **Parallel-safe by canticle:** the only write target is
`11-presence/<canticle>/NN.txt`, so per-canticle runs write to disjoint subdirectories over read-only
inputs and can run concurrently (one process per canticle; do not run the same canticle twice at once).

## Measured result

Full build, all 100 cantos — `5903` roster figures across `1796` scenes, **every scene passing the
closed-set and basis-geometry check** (`0` flagged, recomputed offline):

| canticle | cantos | scenes | figures | present | mentioned | no-cast | anchor agree |
|---|---|---|---|---|---|---|---|
| inferno    | 34 | 588 | 2075 | 1438 | 637 |  6 | 581/608 (95.6%) |
| purgatorio | 33 | 616 | 1988 | 1286 | 702 | 15 | 546/579 (94.3%) |
| paradiso   | 33 | 592 | 1840 |  895 | 945 | 23 | 343/421 (81.5%) |
| **total**  |100 |1796 |5903 |3619 |2284 | 44 |1470/1608 (91.4%) |

- **The closed set does real work.** The check is structurally total — every one of the 5903 roster
  figures is labeled exactly once, none outside the roster, every `basis` inside its scene. On the
  Inferno-1 smoke test, 4 of 20 scenes self-corrected on in-conversation retry before passing, so the
  retry loop is load-bearing, not decorative.
- **Soft anchors mostly agree, and the gap tracks canticle character.** Of `1608` figures that are a
  speaker or `literal`-frame subject (present by definition), `138` were labeled `mentioned`. The
  disagreement is concentrated in **Paradiso** (78, 18.5%), where the action frame is dominated by
  named-but-absent souls and theological referents quoted or expounded rather than bodily on stage —
  exactly the `reported` / `prophecy` nuance that made this check soft, not fatal. Inferno and
  Purgatorio agree at ~95%.
- **The present/mentioned ratio inverts across the journey** (not tuned): Inferno is mostly *present*
  cast (1438:637 — the pilgrim meets souls face to face), while Paradiso tips to *mentioned*
  (895:945 — its discourse names far more figures than stand on its spheres). Presence, derived from
  the text alone, recovers the change in how each canticle stages its people.

Spotlight on **Inferno 1** (the hand-written reference lock, `ref/inferno-01.toml`): present cast =
Dante + Virgilio (from the encounter at line 61); the swimmer (22-30) and miser (49-60) simile
vehicles are excluded as non-cast (dropped at the roster step, not classified); the
historical/prophesied figures (Iulio, Augusto, Enea, Cammilla, Eurialo, Turno, Niso) and the invoked
Beatrice / Dio / San Pietro resolve to `mentioned`; the Veltro prophecy (100-105) names no person
node and writes the empty-cast marker. This matches the reference's cast vs refer/simile split
structurally — present cast, named-but-absent referents, and similes each in the right bucket —
differing only in name form (source spelling here, anglicized in the reference). Structural
agreement, not string-exact, is the bar (per the name-form difference).

## Notes

- `load_presence` and `PRESENCE_LINE_RE` live in `dante_analyze/checkpoint.py`, beside
  `load_locations` — reused parsing belongs in the package, not in a pass script (ARCHITECTURE
  "Shared Code"; feedback memory `feedback_shared_library_reuse`).
- No carry-forward / recap (unlike `09-location`): presence is a per-scene judgment, not narrative
  state that persists, so the driver is the bare per-scene checkpoint loop.
- The present/mentioned split is the person analogue of `10-topography`'s same/new boundary in the
  place pipeline. Addressee (who a speech span is *directed at*) is a distinct judgment deferred to
  `12-addressee`, to keep one judgment per script.
