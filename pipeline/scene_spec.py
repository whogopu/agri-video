"""Scene specs: a structured description of one shot, written before any image prompt.

A spec names every hand's job, every object and what holds it up, and every moving material from its
source to where it lands (bakeoff/shots.yaml documents the slots). `lint()` refuses a spec that leaves
any of that open, because the image models fill gaps with something (a closed fist, an upright bucket
"pouring", a third hand). `render()` turns a spec into one natural-language prompt, in the order
framing → setting → crop → people (body, clothes, posture, each hand) → objects → flows → contacts → style.
The rendered prompt then goes through visual_rules.lint (no negations, known risky words).

Used by the bake-off (bakeoff/shots.yaml, which documents every slot) and by production: a shot in
episode.json with `spec` instead of `image_prompt` gets its prompt from here (pipeline/images.py).
A person with `cast: <id>` is a recurring character: `for_cast()` replaces their clothes with the
character's fixed wardrobe and drops age/build (the reference image and preamble set face and body),
so such a person needs no clothes/age/build in the spec.

    uv run python -m pipeline.scene_spec bakeoff/shots.yaml            # lint + render all, word counts
    uv run python -m pipeline.scene_spec bakeoff/shots.yaml --shot B01 # print one prompt
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from pipeline.visual_rules import expand, lint as prompt_lint

FLOW_WORDS = re.compile(r"\b(pour\w*|scatter\w*|spray\w*|broadcast\w*|stream\w*|sprinkl\w*|throw\w*|fling\w*)\b", re.I)
FLOW_SOURCES = re.compile(r"\b(open|tilted|mouth|nozzle|neck|rim|fingers|spout)\b", re.I)
STOP = {"with", "from", "that", "this", "small", "large", "long", "short", "white", "steel", "plain", "clean",
        "empty", "their", "about", "over", "into", "held", "holding", "sheet", "edge"}


def load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP}


def _all_text(shot: dict[str, Any]) -> str:
    keep = {k: v for k, v in shot.items() if k not in ("inspector_notes", "source", "title", "id")}
    return yaml.safe_dump(keep, allow_unicode=True)


def cast_ids(shot: dict[str, Any]) -> list[str]:
    """Recurring characters in a spec (people with `cast:`), in order = reference image order."""
    return [p["cast"] for p in shot.get("people") or [] if p.get("cast")]


def for_cast(shot: dict[str, Any], chars: list[Any]) -> dict[str, Any]:
    """A copy of the spec for an edit-mode generation: each `cast:` person wears the character's fixed
    wardrobe and loses age/build (the reference sets them). `chars` are CastMember objects for cast_ids()."""
    s = copy.deepcopy(shot)
    by_id = {c.id: c for c in chars}
    for p in s.get("people") or []:
        if p.get("cast"):
            c = by_id[p["cast"]]
            p["clothes"] = c.wardrobe
            p.pop("age", None)
            p.pop("build", None)
    return s


def spec_text(shot: dict[str, Any]) -> str:
    """The spec's prompt-relevant text with {kind:key} tokens unexpanded (for must-show rules)."""
    return _all_text({k: v for k, v in shot.items() if k != "inspector_notes"})


def lint(shot: dict[str, Any], label: str | None = None) -> list[str]:
    """Problems that make a spec incomplete. Empty list = ready to render."""
    errs: list[str] = []
    sid = label or shot.get("id", "?")
    for key in ("teaches", "framing", "setting"):
        if not str(shot.get(key) or "").strip():
            errs.append(f"{sid}: missing {key}")
    objects = shot.get("objects") or []
    obj_words: set[str] = set()
    for i, o in enumerate(objects):
        if not o.get("name"):
            errs.append(f"{sid}: object {i} has no name")
            continue
        if not str(o.get("support") or "").strip():
            errs.append(f"{sid}: object '{o['name'][:40]}' has no support (what holds it up or what it rests on)")
        obj_words |= _words(expand(str(o["name"])))
    for p in shot.get("people") or []:
        who = p.get("role", "person")
        if p.get("gender") not in ("man", "woman"):
            errs.append(f"{sid}: {who}: gender must be man or woman")
        for k in ("posture",) if p.get("cast") else ("clothes", "posture"):
            if not p.get(k):
                errs.append(f"{sid}: {who}: missing {k}")
        for side in ("left_hand", "right_hand"):
            h = p.get(side)
            if not isinstance(h, dict) or not str(h.get("grip") or "").strip():
                errs.append(f"{sid}: {who}: {side} not accounted for (give its grip / where it rests)")
                continue
            holds = h.get("holds")
            if holds and not (_words(str(holds)) & obj_words):
                errs.append(f"{sid}: {who}: {side} holds '{holds}' but no object in objects[] matches it")
    flows = shot.get("flows") or []
    text = _all_text({k: v for k, v in shot.items() if k != "flows"})
    if FLOW_WORDS.search(text) and not flows:
        errs.append(f"{sid}: something pours/scatters/sprays but flows[] is empty")
    for f in flows:
        for k in ("material", "source", "landing"):
            if not f.get(k):
                errs.append(f"{sid}: flow missing {k}")
        if f.get("source") and not FLOW_SOURCES.search(str(f["source"])):
            errs.append(f"{sid}: flow source '{f['source']}' must name an open hand, a tilted container mouth or a nozzle")
    return errs


def _sentence(text: str) -> str:
    text = str(text).strip().rstrip(".;, ")
    return (text[:1].upper() + text[1:] + ".") if text else ""


def _person(p: dict[str, Any], many: bool) -> str:
    pro = "He" if p["gender"] == "man" else "She"
    pos = "His" if p["gender"] == "man" else "Her"
    role = p.get("role", "person").replace("_", " ")
    age = str(p.get("age") or "").strip()
    age = f" {age} years old" if age else ""
    intro = f"The {role} is a {p['gender']}{age}"
    if p.get("build"):
        intro += f", {p['build']}"
    parts = [_sentence(intro), _sentence(f"{pro} wears {p['clothes']}")]
    pose = f"{pro} is {p['posture']}"
    if p.get("gaze"):
        pose += f", {p['gaze']}"
    parts.append(_sentence(pose))
    for side, label in (("left_hand", "left hand"), ("right_hand", "right hand")):
        parts.append(_sentence(f"{pos} {label}: {p[side]['grip']}"))
    return " ".join(parts)


def _object(o: dict[str, Any]) -> str:
    name = expand(str(o["name"])).strip()
    count = int(o.get("count") or 1)
    if not re.match(r"^(a|an|one|two|three)\b", name, re.I):
        name = ("one " if count == 1 else f"{count} ") + name
    bits = [name] + [str(o[k]) for k in ("state", "support") if o.get(k)]
    return _sentence(", ".join(bits))


def render(shot: dict[str, Any], style: str = "") -> str:
    """One natural-language prompt from a spec (tokens expanded)."""
    people = shot.get("people") or []
    parts = [_sentence(shot["framing"]), _sentence(expand(shot["setting"]))]
    if shot.get("crop_stage"):
        parts.append(_sentence("In the field: " + expand(str(shot["crop_stage"]))))
    parts += [_person(p, len(people) > 1) for p in people]
    parts += [_object(o) for o in shot.get("objects") or []]
    for f in shot.get("flows") or []:
        bits = [f["material"], f["source"]] + [f[k] for k in ("path", "landing") if f.get(k)]
        parts.append(_sentence(", ".join(str(b) for b in bits)))
    parts += [_sentence(c) for c in shot.get("contacts") or []]
    if style:
        parts.append(_sentence(style))
    return expand(" ".join(p for p in parts if p))


def check(shot: dict[str, Any], style: str = "", label: str | None = None) -> tuple[list[str], list[str], str]:
    """(errors, warnings, prompt): spec lint + prompt lint on the rendered text."""
    sid = label or shot.get("id", "?")
    errs = lint(shot, sid)
    if errs:
        return errs, [], ""
    prompt = render(shot, style)
    p_errs, warns = prompt_lint(prompt)
    return [f"{sid}: {e}" for e in p_errs], [f"{sid}: {w}" for w in warns], prompt


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("specs", type=Path)
    ap.add_argument("--shot")
    a = ap.parse_args(argv)
    data = load(a.specs)
    bad = False
    for shot in data.get("shots") or []:
        if a.shot and shot.get("id") != a.shot:
            continue
        errs, warns, prompt = check(shot, data.get("style", ""))
        for w in warns:
            print("  warning", w, file=sys.stderr)
        if errs:
            bad = True
            print("\n".join("  ERROR " + e for e in errs), file=sys.stderr)
            continue
        if a.shot:
            print(prompt)
        else:
            print(f"{shot['id']}  {len(prompt.split()):3d} words  OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
