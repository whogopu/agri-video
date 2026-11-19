"""Validate an episode: schema, [VERIFY] markers, length, sources, and stage completeness.

    uv run python -m pipeline.validate episodes/<id>
    uv run python -m pipeline.validate episodes/<id> --as script_approved   # check as if at that status
    uv run python -m pipeline.validate episodes/<id> --set-status script_approved  # validate, then advance

Exit code 1 if there are errors. Status can only be advanced with --set-status when
validation at the target status passes, so the pipeline cannot move past the script
stage while any [VERIFY remains.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from pipeline.common import (
    format_config, load_config, voice_preset, resolve_episode_dir, save_episode, setup_logging, stage_timer,
)
from pipeline.schema import Episode, Scene, Status

VERIFY_RE = re.compile(r"\[\s*VERIFY", re.IGNORECASE)
DIGIT_RE = re.compile(r"[0-9०-९]")  # ASCII and Devanagari digits
DEFAULT_WPM = 140  # used only if neither the episode voice nor its preset has a measured wpm
SCENE_SEC_RANGE = (4.0, 14.0)  # warn outside this (target is 6–12 s)
MAX_ON_SCREEN_WORDS = 4


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        out = [f"ERROR  {m}" for m in self.errors] + [f"WARN   {m}" for m in self.warnings]
        out += [f"info   {m}" for m in self.info]
        verdict = "PASS" if self.ok else "FAIL"
        out.append(f"{verdict}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(out)


def count_words(text: str) -> int:
    """Whitespace tokens that contain at least one letter or digit (skips '।', '-', etc.)."""
    return sum(1 for tok in text.split() if any(ch.isalnum() for ch in tok))


def _source_path(ep_dir: Path, ref: str) -> Path:
    return ep_dir / ref.split("#", 1)[0]


def _check_verify(ep_dir: Path, raw_json: str, rep: Report) -> None:
    for name, text in [("episode.json", raw_json), ("script.md", _read(ep_dir / "script.md"))]:
        for lineno, line in enumerate(text.splitlines(), 1):
            if VERIFY_RE.search(line):
                rep.error(f"{name}:{lineno} unresolved [VERIFY]: {line.strip()[:120]}")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _check_script(ep: Episode, ep_dir: Path, cfg: dict, rep: Report) -> None:
    if not ep.scenes:
        rep.error("episode has no scenes")
        return
    if not ep.title_hi.strip():
        rep.warn("title_hi is empty")

    fcfg = format_config(cfg, ep.format)
    wpm = episode_wpm(ep, cfg)
    lo_s, hi_s = fcfg["target_sec"]
    lo, hi = round(lo_s * wpm / 60), round(hi_s * wpm / 60)
    total = sum(count_words(s.narration_display) for s in ep.scenes)
    est_min = total / wpm
    rep.info.append(f"format: {ep.format} ({ep.video.width}x{ep.video.height})")
    rep.info.append(f"{len(ep.scenes)} scenes, {total} words (~{est_min:.1f} min at {wpm:.0f} wpm, voice {ep.voice.speaker or '?'})")
    if not lo <= total <= hi:
        rep.warn(f"total word count {total} is outside target range {lo}–{hi}")

    if fcfg.get("max_sec") and est_min * 60 > fcfg["max_sec"]:
        rep.warn(f"estimated {est_min * 60:.0f}s exceeds the {ep.format} limit of {fcfg['max_sec']}s")
    if ep.scenes[0].purpose != "hook":
        rep.warn(f"scene {ep.scenes[0].id}: first scene should be the hook (is {ep.scenes[0].purpose!r})")
    if ep.scenes[-1].purpose != "cta":
        rep.warn(f"scene {ep.scenes[-1].id}: last scene should be the CTA (is {ep.scenes[-1].purpose!r})")
    cta = cfg["script"].get("cta_hi", "").strip()
    if cta and not any(cta in s.narration_display for s in ep.scenes if s.purpose == "cta"):
        rep.warn("no cta scene contains the CTA line from config.yaml")

    factual = set(cfg["script"].get("factual_purposes", []))
    for s in ep.scenes:
        _check_scene_script(s, ep_dir, factual, rep, wpm)


def episode_wpm(ep: Episode, cfg: dict) -> float:
    if ep.voice.wpm:
        return float(ep.voice.wpm)
    presets = cfg["tts"].get("voices", {})
    if ep.voice.preset in presets:
        return float(presets[ep.voice.preset].get("wpm") or DEFAULT_WPM)
    return DEFAULT_WPM


def _check_scene_script(s: Scene, ep_dir: Path, factual: set[str], rep: Report, wpm: float = DEFAULT_WPM) -> None:
    tag = f"scene {s.id}"
    words = count_words(s.narration_display)
    est = words / (wpm / 60)
    if not SCENE_SEC_RANGE[0] <= est <= SCENE_SEC_RANGE[1]:
        rep.warn(f"{tag}: {words} words ≈ {est:.1f}s; scenes should be about 6–12s")

    needs_source = s.purpose in factual or bool(DIGIT_RE.search(s.narration_display))
    if needs_source and not s.sources:
        why = f"purpose {s.purpose!r}" if s.purpose in factual else "contains a number"
        rep.error(f"{tag}: no sources listed ({why})")
    for ref in s.sources:
        if not _source_path(ep_dir, ref).exists():
            rep.error(f"{tag}: source file not found: {ref}")

    if s.on_screen_text and count_words(s.on_screen_text) > MAX_ON_SCREEN_WORDS:
        rep.warn(f"{tag}: on_screen_text has more than {MAX_ON_SCREEN_WORDS} words")


def _check_spoken(ep: Episode, rep: Report) -> None:
    for s in ep.scenes:
        if not s.narration_spoken.strip():
            rep.error(f"scene {s.id}: narration_spoken is empty (run text normalization)")
        elif DIGIT_RE.search(s.narration_spoken):
            rep.error(f"scene {s.id}: narration_spoken still contains digits")
        elif re.search(r"[A-Za-z]", s.narration_spoken):
            rep.warn(f"scene {s.id}: narration_spoken has Latin letters; TTS may mispronounce them "
                     "(add a pronunciation.yaml entry)")


def _check_narrated(ep: Episode, ep_dir: Path, rep: Report) -> None:
    for s in ep.scenes:
        tag = f"scene {s.id}"
        if s.audio is None:
            rep.error(f"{tag}: no audio")
            continue
        if not (ep_dir / s.audio.file).exists():
            rep.error(f"{tag}: audio file missing: {s.audio.file}")
        if not s.captions:
            rep.error(f"{tag}: no captions")
        elif s.captions[-1].end > s.audio.duration_sec + 0.05:
            rep.error(f"{tag}: captions run past audio end ({s.captions[-1].end:.2f}s > {s.audio.duration_sec:.2f}s)")


def _check_visuals(ep: Episode, ep_dir: Path, rep: Report) -> None:
    from pipeline.broll import LIBRARY, entry_problems, load_index
    library = {c["id"]: c for c in load_index(LIBRARY)["clips"]}
    used_broll: list[tuple[str, float, float, int]] = []
    for s in ep.scenes:
        tag, v = f"scene {s.id}", s.visual
        if v.type is None:
            rep.error(f"{tag}: visual.type not set")
        elif v.type == "image":
            if not v.image_prompt:
                rep.error(f"{tag}: image scene without image_prompt")
            if v.seed is None:
                rep.error(f"{tag}: image scene without seed")
            if not s.image_file or not (ep_dir / s.image_file).exists():
                rep.error(f"{tag}: image_file missing: {s.image_file}")
            else:
                insp = v.inspection
                if insp is None:
                    rep.error(f"{tag}: image not inspected (images --scene {s.id} --crops, then --inspect pass|fail)")
                elif insp.file_sha1 != hashlib.sha1((ep_dir / s.image_file).read_bytes()).hexdigest():
                    rep.error(f"{tag}: image changed after its inspection; inspect it again")
                elif not insp.passed:
                    rep.error(f"{tag}: image FAILED inspection ({insp.notes}); retry, swap visual, or ask the user")
        elif v.type == "broll":
            if not v.broll_id or v.in_sec is None or v.out_sec is None:
                rep.error(f"{tag}: broll scene needs broll_id, in_sec and out_sec")
            else:
                clip = library.get(v.broll_id)
                if clip is None:
                    rep.error(f"{tag}: broll_id {v.broll_id!r} is not in assets/broll/index.json")
                else:
                    probs = entry_problems(clip, LIBRARY)
                    if probs:
                        rep.error(f"{tag}: clip {v.broll_id} is not usable yet ({'; '.join(probs)})")
                    if v.out_sec > clip["duration_sec"] + 0.01:
                        rep.error(f"{tag}: out_sec {v.out_sec} is past the end of {v.broll_id} ({clip['duration_sec']}s)")
                    if clip.get("people_visible"):
                        rep.warn(f"{tag}: clip {v.broll_id} shows identifiable people — confirm written consent")
                for bid, a, b, other in used_broll:
                    if bid == v.broll_id and v.in_sec < b and a < v.out_sec:
                        rep.error(f"{tag}: reuses clip {bid} segment already used in scene {other}")
                used_broll.append((v.broll_id, v.in_sec, v.out_sec, s.id))
        elif v.type == "graphic":
            if not v.template or not v.props:
                rep.error(f"{tag}: graphic scene needs template and props")


def validate(ep_dir: Path, as_status: Status | None = None) -> tuple[Report, Episode | None]:
    rep = Report()
    cfg = load_config()
    path = ep_dir / "episode.json"
    if not path.exists():
        rep.error(f"{path} not found")
        return rep, None
    raw = path.read_text(encoding="utf-8")

    _check_verify(ep_dir, raw, rep)

    try:
        ep = Episode.model_validate(json.loads(raw))
    except json.JSONDecodeError as e:
        rep.error(f"episode.json is not valid JSON: {e}")
        return rep, None
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            rep.error(f"schema: {loc}: {err['msg']}")
        return rep, None

    status = as_status or ep.status
    rep.info.append(f"validated as status: {status.value}")
    _check_script(ep, ep_dir, cfg, rep)
    if status.at_least(Status.script_approved):
        _check_spoken(ep, rep)
    if status.at_least(Status.narrated):
        _check_narrated(ep, ep_dir, rep)
    if status.at_least(Status.visuals_ready):
        _check_visuals(ep, ep_dir, rep)
    for st, rel in [(Status.draft_rendered, "render/draft.mp4"), (Status.final_rendered, "render/video.mp4"),
                    (Status.reviewed, "review/review.md"), (Status.packaged, "render/thumbnail.png"),
                    (Status.packaged, "youtube.md")]:
        if status.at_least(st) and not (ep_dir / rel).exists():
            rep.error(f"{rel} missing (needed for status {st.value})")
    if status.at_least(Status.reviewed) and "TODO" in _read(ep_dir / "review" / "review.md"):
        rep.error("review/review.md still has TODO items")
    return rep, ep


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--as", dest="as_status", type=Status, help="validate as if at this status")
    g.add_argument("--set-status", type=Status, help="validate at this status, then write it if it passes")
    args = p.parse_args()
    setup_logging()

    ep_dir = resolve_episode_dir(args.episode)
    target = args.set_status or args.as_status
    with stage_timer(ep_dir, "validate") as run:
        rep, ep = validate(ep_dir, target)
        print(rep.render())
        run.note(f"{'PASS' if rep.ok else 'FAIL'} as {target.value if target else 'current status'}: "
                 f"{len(rep.errors)} errors, {len(rep.warnings)} warnings")
        if not rep.ok:
            sys.exit(1)
        if args.set_status and ep is not None:
            old = ep.status
            ep.status = args.set_status
            save_episode(ep_dir, ep)
            run.note(f"status {old.value} → {ep.status.value}")
            print(f"status: {old.value} → {ep.status.value}")


if __name__ == "__main__":
    main()
