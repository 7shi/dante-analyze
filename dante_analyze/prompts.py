"""Prompt builders: `build_reason_prompt` constructs the Turn-1 free-interpretation
user message shared by reading.py, bullets.py, and tags.py."""


def build_reason_prompt(canto, canto_title, s, e, scene_name, tagged, prior, recap):
    """Free English reasoning over one tagged scene. reading.py calls it to GENERATE
    the interpretation; digest.py calls it with `prior=recap=""` to RECONSTRUCT the
    user turn that the committed reading answers. Carries this canto's earlier
    material (`prior`) and the previous canto's recap so prior scenes are nameable."""
    ctx = ""
    if recap:
        ctx += f"""Where things stand at the start of this canto (carried from the previous canto):

{recap}

"""
    if prior:
        ctx += f"""The reading of this canto so far (earlier scenes), for continuity:

{prior}

"""
    return f"""You are an expert reader of Dante's Divina Commedia (Inferno, Purgatorio, Paradiso).

This is Canto {canto} — "{canto_title}". {ctx}Here is scene "{scene_name}" (lines {s}-{e}).
Some words carry a NUMBERED TAG inside brackets or braces: `[n:word]` is a pronoun,
`{{n:phrase}}` a person-naming noun phrase. The number n identifies that reference;
you will refer to it later as `[n]`.

```
{tagged}
```

Think in plain English about what happens in this scene: who does what, who speaks
to whom, and — for EACH numbered tag — which person it refers to. Resolve a pronoun
or epithet to the PERSON it stands for, using the surrounding narrative, the earlier
scenes above, and your knowledge of the poem. A tag that names a person directly
(e.g. `{{4:Virgilio}}`) resolves to that person. The first-person narrator and
protagonist of the poem is Dante himself (the pilgrim-author): his `io`/`i'`/`mi`/`me`
resolve to Dante — unless the `io` falls inside another character's speech, where it
is that speaker. A figure with no proper name in the text — God, a soul not yet named,
a personified beast — is tracked by its source epithet (God who reigns above is
`l'imperador`), not left unidentified. Write freely; this is not the final output yet."""


def _lock_vocabulary(lock_scene):
    """The closed who/where vocabulary of one 14-lock scene, rendered for the digest prompt:
    the names that may appear (cast + speech parties), the setting, and the resident soul-class.
    `lock_scene` is one entry from `load_lock(...)["scenes"]`."""
    names = []
    for fig in lock_scene.get("cast", []):
        who, status = fig["who"], fig.get("status", "")
        names.append(f"{who} ({status})" if status else who)
    for sp in lock_scene.get("speech", []):
        for party in (sp.get("speaker"), sp.get("addressee")):
            if party and party not in ("(none)", "(unattributed)") and party not in names:
                names.append(party)
    setting = lock_scene.get("location") or lock_scene.get("region") or ""
    region = lock_scene.get("region") or ""
    cohort = ", ".join(lock_scene.get("cohort", []))
    lines = []
    lines.append("Figures (only these may be named; `(present)` = on stage, `(mentioned)` = named "
                 "but absent):")
    lines += [f"  - {n}" for n in names] or ["  - (none)"]
    lines.append(f"Setting (the place this scene is in): {setting or '(unspecified)'}")
    if region and region != setting:
        lines.append(f"Region: {region}")
    if cohort:
        lines.append(f"Resident souls of this place: {cohort}")
    return "\n".join(lines)


def build_digest_prompt(scene_name, s, e, lock_scene, prior_digest):
    """Turn-2 of the digest conversation: after the committed 03-reading has been replayed as the
    assistant's prior turn (the events), ask for a 1-2 sentence retelling CONSTRAINED to the scene's
    14-lock entry — the closed who/where vocabulary. The lock is the backbone: the digest may not
    introduce a proper name, place, or soul-class the lock does not list for this scene. `prior_digest`
    is the digest text of earlier scenes this canto, for continuity."""
    cont = ""
    if prior_digest:
        cont = f"""The digest of this canto so far (earlier scenes), for continuity:

{prior_digest}

"""
    vocab = _lock_vocabulary(lock_scene)
    return f"""{cont}Now retell scene "{scene_name}" (lines {s}-{e}) as a DIGEST: one or two sentences
at story-reading density — more than a plot summary, lighter than a translation. English prose.

Use ONLY the following identity-and-setting scaffold for this scene. It fixes WHO is here and
WHERE we are; your reading above supplies WHAT happens:

{vocab}

Rules:
- Name figures only from the list above, in their source spelling exactly as written
  (e.g. `Virgilio`, not `Virgil`; `Minòs`, keep the accents). Do NOT introduce any other
  proper name, place, or group not listed.
- Keep the setting consistent with the scaffold; do not invent a location.
- A `(mentioned)` figure is named but not bodily present — refer to them as merely spoken of, not
  acting on stage.
- Output ONLY the one or two sentences of the retelling, no preamble, no list, no commentary."""


def build_digest_translate_prompt(en_sentence, lock_names):
    """Render the committed English digest sentence into natural Japanese narrative prose, keeping
    every proper name in its SOURCE spelling (so the lock-conformance vocabulary is preserved across
    languages). `lock_names` is the list of names the sentence may carry, for the model's reference."""
    keep = ", ".join(lock_names) if lock_names else "(none)"
    return f"""次の英語のダイジェスト文を、自然な日本語の物語散文に翻訳してください。

英語:
{en_sentence}

規則:
- 固有名（人物・場所・魂の集団）は **原綴りのまま** 残すこと（例: Virgilio, Minòs, Dante）。
  日本語に訳したり読みを当てたりしない。アクセント記号も保持する。
- この文に現れてよい固有名: {keep}
- 1〜2文の物語散文として、英語と同じ密度で訳す。
- 訳文だけを出力する。前置き・注釈・箇条書きは付けない。"""
