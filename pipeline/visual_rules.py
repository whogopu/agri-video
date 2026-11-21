"""Image prompt rules: tested prompt phrases, a prompt lint, and per-shot must-show assertions.

One file, assets/visual_rules.yaml, feeds both sides of the image stage so they can't drift apart:
- generation: `{kind:key}` tokens in a shot's image_prompt expand to phrases that were A/B tested on
  FLUX.2 klein (settings, crop stages, props, actions), and `lint()` blocks prompts that name what
  they don't want ("no palm trees"), since klein runs without a negative prompt (guidance 1.0) and
  naming a thing tends to put it in the picture (A/B 2026-11-20, docs/ARCHITECTURE.md §7.6c);
- inspection: `must_show()` lists what this shot's picture has to show, from the tokens the prompt
  uses and from narration keywords (e.g. कटाई → bare stubble, no standing crop). `images --checklist`
  prints it for one shot.

After a failed inspection, fix or add the entry here, so the same mistake doesn't come back.

    uv run python -m pipeline.visual_rules --lint "Ramesh walks ... no palm trees"
    uv run python -m pipeline.visual_rules --expand "{setting:north_field_bg}"
    uv run python -m pipeline.visual_rules --list
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from pipeline.common import REPO_ROOT

RULES_PATH = REPO_ROOT / "assets" / "visual_rules.yaml"
KINDS = ("setting", "stage", "prop", "action")
TOKEN = re.compile(r"\{([a-z]+):([a-z0-9_]+)\}")
# Words that tell the model what to leave out. klein has no negative prompt, so they backfire.
NEGATION = re.compile(r"\b(no|not|without|nothing|none|never|neither|nor|free of|avoid|instead of|except)\b|n't\b",
                      re.IGNORECASE)


@dataclass
class Rules:
    phrases: dict[str, dict[str, dict[str, Any]]]      # kind → key → {text, must_show, tested}
    risky_words: list[dict[str, Any]]                   # {word, why}
    narration: list[dict[str, Any]]                     # {id, when_any, must_show, hint}
    source: Path = field(default=RULES_PATH)


@lru_cache(maxsize=4)
def _load(path_str: str, mtime: float) -> Rules:
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}
    phrases = {k: dict(data.get(f"{k}s") or {}) for k in KINDS}
    return Rules(phrases, list(data.get("risky_words") or []), list(data.get("narration") or []), Path(path_str))


def load_rules(path: Path | None = None) -> Rules:
    p = Path(path or RULES_PATH)
    if not p.exists():
        return Rules({k: {} for k in KINDS}, [], [], p)
    return _load(str(p), p.stat().st_mtime)


def tokens(prompt: str) -> list[tuple[str, str]]:
    return TOKEN.findall(prompt or "")


def expand(prompt: str, rules: Rules | None = None) -> str:
    """Replace every {kind:key} with its phrase. Unknown tokens raise (lint reports them first)."""
    rules = rules or load_rules()

    def sub(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        entry = rules.phrases.get(kind, {}).get(key)
        if entry is None:
            raise KeyError(f"unknown prompt token {{{kind}:{key}}} (see {rules.source.name})")
        return str(entry["text"]).strip().rstrip(".")
    return TOKEN.sub(sub, prompt or "")


def lint(prompt: str, rules: Rules | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one image prompt. Errors block generation. Checked on the prompt as
    written and after token expansion, so library phrases are held to the same rule."""
    rules = rules or load_rules()
    errors: list[str] = []
    warnings: list[str] = []
    for kind, key in tokens(prompt):
        if kind not in KINDS:
            errors.append(f"unknown token kind {{{kind}:{key}}}: use one of {', '.join(KINDS)}")
        elif key not in rules.phrases[kind]:
            known = ", ".join(sorted(rules.phrases[kind])) or "none yet"
            errors.append(f"unknown token {{{kind}:{key}}}; known {kind}s: {known}")
    if errors:
        return errors, warnings
    text = expand(prompt, rules)
    negs = sorted({m.group(0).lower() for m in NEGATION.finditer(text)})
    if negs:
        bits = []
        for m in NEGATION.finditer(text):
            a, b = max(0, m.start() - 15), min(len(text), m.end() + 25)
            bits.append("…" + text[a:b].strip() + "…")
        errors.append(
            f"prompt names what it doesn't want ({', '.join(negs)}): {'; '.join(bits[:4])}. FLUX.2 klein has no "
            "negative prompt, so naming a thing tends to add it. Describe what IS there instead "
            "(e.g. 'bare wrists' for 'no wristwatch', '{setting:north_field_bg}' for 'no palm trees')")
    low = TOKEN.sub(" ", prompt or "").lower()   # only the words written in the shot; library phrases are tested
    for r in rules.risky_words:
        if re.search(rf"\b{re.escape(str(r['word']).lower())}\b", low):
            warnings.append(f"'{r['word']}': {r['why']}")
    return errors, warnings


def must_show(prompt: str, sentence: str = "", rules: Rules | None = None) -> list[str]:
    """What this shot's picture must show: from the library entries its prompt uses and the
    narration rules whose keywords appear in the sentence over it (or in the prompt)."""
    rules = rules or load_rules()
    out: list[str] = []
    for kind, key in tokens(prompt):
        entry = rules.phrases.get(kind, {}).get(key) or {}
        out += [f"[{kind}:{key}] {m}" for m in entry.get("must_show") or []]
    hay = f"{sentence}\n{prompt}".lower()
    for r in rules.narration:
        hit = next((w for w in r.get("when_any") or [] if str(w).lower() in hay), None)
        if hit:
            out += [f"[{r['id']} ← '{hit}'] {m}" for m in r.get("must_show") or []]
    seen, uniq = set(), []
    for m in out:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq


def prompt_hints(sentence: str, prompt: str = "", rules: Rules | None = None) -> list[str]:
    """Library tokens the narration rules suggest for this sentence (shown when writing prompts)."""
    rules = rules or load_rules()
    hay = f"{sentence}\n{prompt}".lower()
    return [f"{r['id']}: {r['hint']}" for r in rules.narration
            if r.get("hint") and any(str(w).lower() in hay for w in r.get("when_any") or [])]


def shot_sentence(scene: dict, shot: dict, shots: list[dict]) -> str:
    """The narration sentence(s) a shot sits over: from its at_segment to the next shot's (episode.json dicts)."""
    text = re.sub(r"\{[a-z]+\}|\|+", "", scene.get("narration_display", "")).strip()
    parts = [p.strip() for p in re.split(r"(?<=[।?!])\s+", text) if p.strip()]
    if not shots or len(shots) < 2 or not parts:
        return text
    starts = sorted(s.get("at_segment", 0) for s in shots)
    a = shot.get("at_segment", 0)
    later = [s for s in starts if s > a]
    b = later[0] if later else len(parts)
    return " ".join(parts[a:b]) or text


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lint", metavar="PROMPT")
    p.add_argument("--expand", metavar="PROMPT")
    p.add_argument("--list", action="store_true", help="list every token with its tested status")
    args = p.parse_args(argv)
    rules = load_rules()
    if args.list:
        for kind in KINDS:
            for key, e in rules.phrases[kind].items():
                print(f"{{{kind}:{key}}}  [{e.get('tested') or 'untested'}]\n    {e['text'].strip()}")
        return
    if args.expand:
        print(expand(args.expand, rules))
    if args.lint:
        errors, warnings = lint(args.lint, rules)
        for e in errors:
            print(f"ERROR  {e}")
        for w in warnings:
            print(f"warn   {w}")
        if not errors and not warnings:
            print("ok")
        raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
