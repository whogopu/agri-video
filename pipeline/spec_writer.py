"""Spec writer: a local LLM fills in one scene spec per shot; code checks it and sends errors back.

Used by pipeline/shot_specs.py (episode shots) and the P4 model comparison. The LLM chooses only the
content of a shot (what it teaches, setting, crop stage, people and their hands, objects, flows, which cast
members appear); framing comes from the shot plan (code) and overwrites whatever the LLM writes.

Per shot the prompt holds: the Hindi sentence(s) under the shot and their neighbours, the scene purpose, the
episode title, the cast (id, gender, role; never face or clothes, the reference image supplies them), the
framing, the visual_rules library tokens with the hints and must-show items matched for the sentence, and the
3–4 most similar approved bake-off specs (bakeoff/shots.yaml) as examples.

Checks (code), errors go back to the LLM for up to shot_specs.max_repair_rounds rounds:
- scene_spec.lint (every hand, object support, flows) and the rendered prompt's visual_rules.lint
  (no negations, known tokens);
- cast ids from this episode's cast, at most max_cast_per_shot, each once;
- stage/setting tokens the narration rules require for the sentence (e.g. कटाई → {stage:harvested_stubble});
  suggested prop/action tokens are warnings only (a sentence naming a report isn't always a report shot).
A shot still failing after the last round keeps its last spec with `flags`: it needs Claude or the user and
images refuses it. Never a silent fallback.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from pipeline import scene_spec
from pipeline.common import REPO_ROOT
from pipeline.visual_rules import load_rules, must_show, prompt_hints, tokens as find_tokens

SLOTS = ("teaches", "framing", "setting", "crop_stage", "people", "objects", "flows", "contacts", "inspector_notes")
PERSON_KEYS = ("role", "cast", "gender", "age", "build", "clothes", "posture", "gaze", "left_hand", "right_hand")
CAST_DROPS = ("age", "build", "clothes")
GENDER = {"man": "man", "male": "man", "boy": "man", "woman": "woman", "female": "woman", "girl": "woman"}
FLOW_ALIASES = {"substance": "material", "target": "landing", "destination": "landing", "from": "source", "to": "landing"}
REQUIRED_KINDS = ("stage", "setting")   # narration-rule hints of these kinds must appear in the spec


@dataclass
class ShotContext:
    key: str                              # e.g. "s16-k1"
    sentence: str                         # Hindi narration under the shot
    framing: str                          # framing text from the shot plan
    topic: str = ""
    purpose: str = ""
    before: str = ""                      # sentence before the shot
    after: str = ""                       # sentence after it
    other_shots: list[str] = field(default_factory=list)   # sentences of the scene's other shots
    cast: list[dict[str, str]] = field(default_factory=list)  # [{id, gender: man|woman, role}]
    exclude_examples: list[str] = field(default_factory=list)  # example ids never shown (evaluation)
    old_spec: dict[str, Any] | None = None   # revise: the spec to rewrite
    note: str = ""                           # revise: failed-inspection notes or the user's note


@dataclass
class SpecResult:
    key: str
    spec: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)     # left after the last round = flags
    warnings: list[str] = field(default_factory=list)
    prompt: str = ""                                    # rendered body (no cast preamble), when it passed
    rounds: int = 0                                     # repair rounds used
    sec: float = 0.0                                    # LLM seconds over all rounds
    answers: list[str] = field(default_factory=list)    # raw LLM answers, one per round

    @property
    def ok(self) -> bool:
        return self.spec is not None and not self.errors


# ---------------------------------------------------------------- examples

def _slot_doc(specs_path: Path) -> str:
    """The slot documentation at the top of bakeoff/shots.yaml (single source)."""
    lines, on = [], False
    for line in specs_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Slots"):
            on = True
            continue
        if on:
            if not line.startswith("#"):
                break
            lines.append(line[2:] if line.startswith("# ") else line[1:])
    return "\n".join(lines).rstrip()


def example_pool(scfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Approved bake-off specs as examples: cast people without age/build/clothes, as the LLM must write them."""
    data = scene_spec.load(REPO_ROOT / scfg.get("example_specs", "bakeoff/shots.yaml"))
    skip = set(scfg.get("example_exclude") or [])
    pool = []
    for s in data.get("shots") or []:
        if s.get("id") in skip:
            continue
        s = copy.deepcopy(s)
        for p in s.get("people") or []:
            if p.get("cast"):
                for k in CAST_DROPS:
                    p.pop(k, None)
        pool.append(s)
    return pool


def _example_words(s: dict[str, Any]) -> set[str]:
    text = " ".join(str(s.get(k) or "") for k in ("title", "teaches", "source")) + " " + scene_spec.spec_text(s)
    return set(re.findall(r"[a-z]{3,}", text.lower()))


def sentence_keywords(sentence: str, scfg: dict[str, Any]) -> set[str]:
    """English keywords for a Hindi sentence (config shot_specs.keywords), for example selection."""
    out: set[str] = set()
    for hi, en in (scfg.get("keywords") or {}).items():
        if hi in sentence:
            out |= {w.lower() for w in en}
    return out


def pick_examples(pool: list[dict[str, Any]], ctx: ShotContext, scfg: dict[str, Any]) -> list[dict[str, Any]]:
    """The examples most similar to the sentence: shared library tokens count double, then keyword overlap.
    Ties keep file order (deterministic)."""
    n = int(scfg.get("examples", 4))
    hint_toks = {t for h in prompt_hints(ctx.sentence) for t in find_tokens(h)}
    kw = sentence_keywords(ctx.sentence, scfg)
    scored = []
    for i, s in enumerate(pool):
        if s.get("id") in ctx.exclude_examples:
            continue
        toks = set(find_tokens(scene_spec.spec_text(s)))
        score = 2 * len(hint_toks & toks) + len(kw & _example_words(s))
        scored.append((-score, i, s))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [s for _, _, s in scored[:n]]


def _example_json(s: dict[str, Any]) -> str:
    return json.dumps({k: s[k] for k in SLOTS if k in s}, ensure_ascii=False)


# ---------------------------------------------------------------- prompts

SYSTEM = """You write SCENE SPECS for still photographs in Hindi farming videos for farmers in North India. A spec is a JSON object; code turns it into the image prompt, so you fill in slots and never write a prompt.

Slots:
{slots}

Rules:
- The picture shows what the narration sentence says, so a farmer understands it at a glance: one clear action, correct farming (crop stage, tool, method, a plausible quantity). In a 'mistake' scene, show the mistake plainly as farmers make it.
- Describe only what IS in the picture. Never name what is absent: the words no, not, without, never, nothing, none, free of, avoid, instead of, except are forbidden anywhere (the image model draws whatever is named).
- Every person: role, gender ("man" or "woman"), posture, gaze, and both left_hand and right_hand as {{"holds": <object name or null>, "grip": <what the hand does or where it rests>}}. A hand's "holds" must name an object listed in objects[].
- Every object: name, count, state, support (who holds it or what it rests on).
- Anything poured, scattered, thrown or sprayed: one flows[] entry {{"material", "source", "path", "landing"}}; the source names an open hand, the mouth of a tilted container or a nozzle.
- People: usually 1 or 2, at most 3. Recurring characters are written "cast": "<id>" with role, gender, posture, gaze and both hands only: their face, age, build and clothes come from a reference photo, so leave out age, build and clothes for them. At most {max_cast} cast members, each once. Use a cast member only where the role fits the place (a lab technician belongs in a lab or at a KVK). Anyone else is not cast: give age, build and rural North Indian clothes.
- Text in the picture is never readable: write 'printed text too small to read' on reports, labels and charts.
- Use the library tokens below where they fit, written exactly like {{stage:harvested_stubble}}; they are tested phrases.
- "framing" is given: copy it exactly.
- inspector_notes: 1-3 short things an inspector must check in the image (never sent to the image model).

Library tokens:
{tokens}

Answer with ONLY the JSON object."""


def _token_list() -> str:
    rules = load_rules()
    out = []
    for kind, entries in rules.phrases.items():
        for key, e in entries.items():
            text = " ".join(str(e.get("text", "")).split())
            out.append(f"{{{kind}:{key}}} = {text[:110]}{'…' if len(text) > 110 else ''}")
    return "\n".join(out)


def system_prompt(scfg: dict[str, Any]) -> str:
    return SYSTEM.format(slots=_slot_doc(REPO_ROOT / scfg.get("example_specs", "bakeoff/shots.yaml")),
                         max_cast=int(scfg.get("max_cast_per_shot", 2)), tokens=_token_list())


def required_tokens(sentence: str) -> list[list[str]]:
    """Token groups the spec must contain (one of each group): stage tokens one by one, setting tokens as
    alternatives (a sentence may name both field and lab)."""
    rules = load_rules()
    hay = sentence.lower()
    stages, settings = [], []
    for r in rules.narration:
        if r.get("hint") and any(str(w).lower() in hay for w in r.get("when_any") or []):
            for kind, key in find_tokens(r["hint"]):
                tok = f"{{{kind}:{key}}}"
                if kind == "stage" and [tok] not in stages:
                    stages.append([tok])
                elif kind == "setting" and tok not in settings:
                    settings.append(tok)
    return stages + ([settings] if settings else [])


def user_prompt(ctx: ShotContext, examples: list[dict[str, Any]]) -> str:
    cast = "\n".join(f'- "{c["id"]}": {c["gender"]}, {c["role"]}' for c in ctx.cast) or "- none (no recurring characters)"
    hints = [h for h in prompt_hints(ctx.sentence)]
    musts = must_show("", ctx.sentence)
    req = required_tokens(ctx.sentence)
    lines = [f"Episode topic: {ctx.topic}" if ctx.topic else "",
             f"Scene purpose: {ctx.purpose}" if ctx.purpose else "",
             f'Narration under this shot (Hindi): "{ctx.sentence}"',
             f'Sentence before it: "{ctx.before}"' if ctx.before else "",
             f'Sentence after it: "{ctx.after}"' if ctx.after else ""]
    if ctx.other_shots:
        lines.append("The scene's other shots show: " + " | ".join(f'"{s}"' for s in ctx.other_shots))
    lines += [f'Framing (copy exactly): "{ctx.framing}"', "Recurring characters you may use:", cast]
    if req:
        lines.append("Required library tokens (put them in setting or crop_stage): " +
                     "; ".join(" or ".join(g) for g in req))
    if hints:
        lines.append("Library tokens suggested for this sentence: " + "; ".join(hints))
    if musts:
        lines.append("The finished picture will be checked for:\n" + "\n".join(f"- {m.split('] ', 1)[-1]}" for m in musts))
    lines.append("\nApproved example specs (other shots):\n" + "\n\n".join(_example_json(e) for e in examples))
    if ctx.old_spec is not None:
        lines.append("\nThe current spec for this shot:\n" + _example_json(ctx.old_spec))
        lines.append(f"Rewrite it to fix this: {ctx.note}\nKeep what already works; change what the note asks.")
    elif ctx.note:
        lines.append(f"\nWrite the spec for this shot. It must fix this: {ctx.note}")
    else:
        lines.append("\nWrite the spec for this shot.")
    return "\n".join(l for l in lines if l)


def repair_prompt(base: str, answer: str, errors: list[str]) -> str:
    return (f"{base}\n\nYour previous answer:\n{answer.strip()}\n\nCode checks rejected it:\n" +
            "\n".join(f"- {e}" for e in errors) + "\n\nReturn the whole corrected JSON object.")


# ---------------------------------------------------------------- parse, normalise, check

def parse_json(text: str) -> dict[str, Any] | None:
    from pipeline.vlm_inspect import parse_json as _p
    return _p(text)


def _hand(h: Any) -> Any:
    if isinstance(h, str):
        return {"holds": None, "grip": h}
    return h


def normalize(raw: dict[str, Any], ctx: ShotContext) -> tuple[dict[str, Any], list[str]]:
    """Known slots only; framing from the plan; cast people stripped of age/build/clothes and given the
    character's gender. Returns (spec, notes about what was changed)."""
    notes: list[str] = []
    spec = {k: copy.deepcopy(raw[k]) for k in SLOTS if k in raw}
    spec["framing"] = ctx.framing
    genders = {c["id"]: c["gender"] for c in ctx.cast}
    people = []
    for p in spec.get("people") or []:
        if not isinstance(p, dict):
            continue
        p = {k: p[k] for k in PERSON_KEYS if k in p}
        if p.get("cast") in (None, "", "null", "none"):
            p.pop("cast", None)
        if p.get("cast"):
            p["cast"] = str(p["cast"]).strip().lower()
            dropped = [k for k in CAST_DROPS if p.pop(k, None)]
            if dropped:
                notes.append(f"{p['cast']}: dropped {', '.join(dropped)} (the reference sets them)")
            if p["cast"] in genders:
                p["gender"] = genders[p["cast"]]
        if isinstance(p.get("gender"), str):
            p["gender"] = GENDER.get(p["gender"].strip().lower(), p["gender"])
        for side in ("left_hand", "right_hand"):
            if side in p:
                p[side] = _hand(p[side])
        people.append(p)
    spec["people"] = people
    spec["objects"] = [o if isinstance(o, dict) else {"name": str(o)} for o in spec.get("objects") or []]
    for o in spec["objects"]:
        m = re.match(r"\s*(\d+)\b", str(o.get("count"))) if isinstance(o.get("count"), str) else None
        if m:
            o["count"] = int(m.group(1))   # "12 visible across the field" → 12
    flows = []
    for f in spec.get("flows") or []:
        if isinstance(f, dict):
            flows.append({FLOW_ALIASES.get(k, k): v for k, v in f.items()})
    spec["flows"] = flows
    for k in ("contacts", "inspector_notes"):
        v = spec.get(k) or []
        spec[k] = [v] if isinstance(v, str) else [str(x) for x in v]
    return spec, notes


def check(spec: dict[str, Any], ctx: ShotContext, scfg: dict[str, Any], style: str) -> tuple[list[str], list[str], str]:
    """(errors, warnings, rendered prompt body) for a normalised spec."""
    from pipeline.cast import load_character
    errors: list[str] = []
    ids = scene_spec.cast_ids(spec)
    allowed = [c["id"] for c in ctx.cast]
    for cid in ids:
        if cid not in allowed:
            errors.append(f'cast "{cid}" is not a recurring character of this episode (allowed: {", ".join(allowed) or "none"}); '
                          "use one of them or describe a person who is not cast, with age, build and clothes")
    if len(ids) != len(set(ids)):
        errors.append("a cast member appears twice; each recurring character at most once")
    mx = int(scfg.get("max_cast_per_shot", 2))
    if len(ids) > mx:
        errors.append(f"{len(ids)} cast members; at most {mx} per shot")
    text = scene_spec.spec_text(spec)
    for group in required_tokens(ctx.sentence):
        if not any(t in text for t in group):
            errors.append(f"the sentence needs {' or '.join(group)} in setting or crop_stage")
    for o in spec.get("objects") or []:
        c = o.get("count")
        if c is not None and not (isinstance(c, int) or (isinstance(c, str) and c.strip().isdigit())):
            errors.append(f"object '{str(o.get('name'))[:40]}': count must be a whole number, got {c!r} "
                          "(for many small things, use count 1 and describe them in the name, e.g. 'a heap of granules')")
    if errors:
        return errors, [], ""
    chars = [load_character(cid) for cid in ids]
    try:
        s_errs, s_warns, prompt = scene_spec.check(scene_spec.for_cast(spec, chars), style, "spec")
    except (KeyError, TypeError, ValueError, AttributeError) as e:   # a malformed slot the lint didn't catch
        return [f"spec could not be rendered ({type(e).__name__}: {e}); check every slot's type against the examples"], [], ""
    warnings = [w.removeprefix("spec: ") for w in s_warns]
    hint_toks = {t for h in prompt_hints(ctx.sentence) for t in find_tokens(h)}
    for kind, key in sorted(hint_toks):
        tok = f"{{{kind}:{key}}}"
        if kind not in REQUIRED_KINDS and tok not in text:
            warnings.append(f"suggested {tok} is not used")
    return [e.removeprefix("spec: ") for e in s_errs], warnings, prompt


# ---------------------------------------------------------------- the loop

LLM = Callable[..., dict[str, dict[str, Any]]]


def write_specs(ctxs: list[ShotContext], cfg: dict[str, Any], llm: LLM | None = None, log: Path | None = None,
                progress: Callable[[str], None] = print) -> dict[str, SpecResult]:
    """One spec per context: first answer + up to max_repair_rounds repair rounds, batched over the shots
    still failing (one model load per round)."""
    if llm is None:
        from pipeline.local_llm import generate as llm
    scfg = cfg["shot_specs"]
    style = cfg["images"].get("style_suffix", "").strip()
    system = system_prompt(scfg)
    pool = example_pool(scfg)
    base = {c.key: user_prompt(c, pick_examples(pool, c, scfg)) for c in ctxs}
    by_key = {c.key: c for c in ctxs}
    results = {c.key: SpecResult(c.key) for c in ctxs}
    pending = [c.key for c in ctxs]
    rounds = int(scfg.get("max_repair_rounds", 3))
    for rnd in range(rounds + 1):
        if not pending:
            break
        jobs = []
        for k in pending:
            r = results[k]
            prompt = base[k] if not r.answers else repair_prompt(base[k], r.answers[-1], r.errors)
            jobs.append({"id": k, "system": system, "prompt": prompt})
        progress(f"spec writer: round {rnd} ({'first answers' if rnd == 0 else 'repair'}), {len(jobs)} shot(s)")
        out = llm(jobs, scfg["model"], max_tokens=scfg.get("max_tokens", 1800),
                  temperature=scfg.get("temperature", 0.2), log=log)
        still = []
        for k in pending:
            r, ans = results[k], out.get(k) or {"error": "no answer"}
            r.rounds = rnd
            r.sec += float(ans.get("sec") or 0)
            text = ans.get("text") or ""
            r.answers.append(text or f"(error: {ans.get('error')})")
            raw = parse_json(text) if text else None
            if raw is None:
                r.errors = [f"no JSON object in the answer ({ans.get('error') or 'unparseable'}); answer with only the JSON object"]
                still.append(k)
                continue
            spec, _ = normalize(raw, by_key[k])
            r.spec = spec
            r.errors, r.warnings, r.prompt = check(spec, by_key[k], scfg, style)
            if r.errors:
                still.append(k)
        pending = still
    return results
