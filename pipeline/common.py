"""Shared helpers: paths, config, episode load/save, logging, stage timing, CLI args."""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import yaml

from pipeline.schema import Episode

REPO_ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = REPO_ROOT / "episodes"
CONFIG_PATH = REPO_ROOT / "config.yaml"
PRONUNCIATION_PATH = REPO_ROOT / "pronunciation.yaml"

log = logging.getLogger("pipeline")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------- config ----------

def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_config(cfg: dict[str, Any], fmt: str) -> dict[str, Any]:
    """Settings for one output format ('long' or 'short') from config.yaml `formats`."""
    try:
        return cfg["formats"][fmt]
    except KeyError:
        raise SystemExit(f"unknown format {fmt!r}; config.yaml defines: {', '.join(cfg['formats'])}")


def voice_preset(cfg: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    """A voice from config.yaml `tts.voices` (default: tts.default_voice), with its name as `preset`."""
    tts = cfg["tts"]
    name = name or tts["default_voice"]
    try:
        return {"preset": name, **tts["voices"][name]}
    except KeyError:
        raise SystemExit(f"unknown voice {name!r}; config.yaml defines: {', '.join(tts['voices'])}")


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------- episode paths ----------

def resolve_episode_dir(arg: str | Path) -> Path:
    """Accept `episodes/<id>`, `<id>`, or a path to episode.json."""
    p = Path(arg)
    if p.name == "episode.json":
        p = p.parent
    if not p.exists() and (EPISODES_DIR / p).exists():
        p = EPISODES_DIR / p
    if not p.is_dir():
        raise SystemExit(f"episode folder not found: {arg}")
    return p.resolve()


def episode_json_path(ep_dir: Path) -> Path:
    return ep_dir / "episode.json"


def load_episode(ep_dir: Path) -> Episode:
    path = episode_json_path(ep_dir)
    with open(path, encoding="utf-8") as f:
        return Episode.model_validate(json.load(f))


def save_episode(ep_dir: Path, episode: Episode) -> None:
    """Validate and write atomically, so a crash mid-write never corrupts episode.json."""
    Episode.model_validate(episode.model_dump())  # re-validate after in-place edits
    write_json(episode_json_path(ep_dir), episode.model_dump(mode="json"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------- log.md + stage timing ----------

def append_log(ep_dir: Path, text: str) -> None:
    with open(ep_dir / "log.md", "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


@dataclass
class StageRun:
    stage: str
    notes: list[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        log.info(msg)
        self.notes.append(msg)


@contextmanager
def stage_timer(ep_dir: Path, stage: str) -> Iterator[StageRun]:
    """Time a stage and append its duration and notes to the episode's log.md,
    including when the stage fails."""
    run = StageRun(stage)
    start = time.monotonic()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outcome = "ok"
    try:
        yield run
    except SystemExit as e:
        outcome = "ok" if e.code in (0, None) else f"failed (exit {e.code})"
        raise
    except BaseException as e:
        outcome = f"failed: {type(e).__name__}: {e}"
        raise
    finally:
        secs = time.monotonic() - start
        lines = [f"\n## {stage} — {started_at}", f"- duration: {secs:.1f}s", f"- outcome: {outcome}"]
        lines += [f"- {n}" for n in run.notes]
        append_log(ep_dir, "\n".join(lines))


# ---------- timing (mirrors remotion/src/timing.ts) ----------

FALLBACK_SCENE_SEC = 4.0


def scene_frames(audio_sec: float | None, fps: int, padding_sec: float, crossfade: int) -> int:
    sec = (audio_sec if audio_sec is not None else FALLBACK_SCENE_SEC) + padding_sec
    return max(int(sec * fps + 0.5), crossfade * 2 + 1)  # JS Math.round for positive numbers


def episode_frames(episode: Episode, cfg: dict[str, Any]) -> int:
    fps, pad = episode.video.fps, float(cfg["video"]["scene_padding_sec"])
    xf = int(cfg["render"]["crossfade_frames"])
    total = sum(scene_frames(s.audio.duration_sec if s.audio else None, fps, pad, xf) for s in episode.scenes)
    return max(1, total - xf * max(0, len(episode.scenes) - 1))


# ---------- CLI ----------

def stage_parser(description: str) -> argparse.ArgumentParser:
    """Standard stage CLI: episode dir, --scene N, --force, -v."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("episode", help="episodes/<id> (or just <id>)")
    p.add_argument("--scene", type=int, action="append", dest="scenes",
                   help="only process this scene id (repeatable)")
    p.add_argument("--force", action="store_true", help="redo outputs that already exist")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def selected_scenes(episode: Episode, scene_ids: list[int] | None):
    if not scene_ids:
        return list(episode.scenes)
    return [episode.scene(i) for i in scene_ids]
