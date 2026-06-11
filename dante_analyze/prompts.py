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
