"""Shot specs stage: plan the shots of every image scene in code, then let a local LLM write each shot's spec.

    uv run python -m pipeline.shot_specs episodes/<id> [--scene N] [--force]       # plan shots + write specs
    uv run python -m pipeline.shot_specs episodes/<id> --plan-only                 # shot plan by code, no LLM

Runs after `narrated` (segment timings are known), on scenes with visual.type == "image". Graphics and
B-roll scenes are untouched. User decisions 2026-11-22 (docs/plans/local-shot-specs.md):

1. The shot plan is code, deterministic, no human or LLM step: how many shots (1–3, one per sentence,
   a too-short sentence merged into a neighbour, every shot shots.min_shot_sec–max_shot_sec on screen,
   measured like common.shot_starts_sec / remotion timing.ts), each shot's at_segment, and its framing
   (a scene opens wide, then medium, then close-up; a one-shot scene is medium-wide; never the same
   framing twice in a row, also across adjacent image scenes). Framing text comes from config
   shot_specs.framings.
2. The local LLM chooses only what each shot shows: the spec content (pipeline/scene_spec.py slots) and
   which cast members appear (at most shot_specs.max_cast_per_shot).

Existing shots are kept unless --force (idempotent and per-scene like every stage).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from pipeline.schema import Episode, Scene

FRAMING_SEQ = {1: ["medium_wide"], 2: ["wide", "medium"], 3: ["wide", "medium", "close"]}
MAX_BOUNDARIES = 12   # 2^12 subsets; a scene never has this many sentences


@dataclass
class PlannedShot:
    at_segment: int
    start: float      # seconds from scene start, lead-in included (as shot_starts_sec)
    end: float
    framing: str      # key in config shot_specs.framings

    @property
    def sec(self) -> float:
        return self.end - self.start


def _times(scene: Scene, lead: float, pad: float) -> tuple[list[float], float]:
    """Cut time before each segment j>=1 (middle of the pause, as shot_starts_sec) and the scene end."""
    audio = scene.audio
    segs = audio.segments if audio else []
    cuts = [lead + (segs[j - 1].end + segs[j].start) / 2 for j in range(1, len(segs))]
    dur = audio.duration_sec if audio else 0.0
    return cuts, lead + dur + pad


def _violation(durs: list[float], lo: float, hi: float) -> float:
    return sum(max(0.0, lo - d) + max(0.0, d - hi) for d in durs)


def plan_cuts(cuts: list[float], end: float, lo: float, hi: float, max_shots: int) -> list[int]:
    """Segment indices where shots start (always [0, ...]). Among all ways to cut at sentence boundaries
    with at most max_shots shots: the plans where every shot lasts lo–hi s win; among those the most
    shots (one per sentence), then the longest shortest shot. If none fits, the smallest total overrun."""
    n = min(len(cuts), MAX_BOUNDARIES)
    best_key, best = None, [0]
    for r in range(0, min(n, max_shots - 1) + 1):
        for combo in itertools.combinations(range(1, n + 1), r):   # segment indices j (cut before segment j)
            edges = [0.0] + [cuts[j - 1] for j in combo] + [end]
            durs = [b - a for a, b in zip(edges, edges[1:])]
            v = _violation(durs, lo, hi)
            key = (v > 1e-9, round(v, 6), -len(durs), -round(min(durs), 6))
            if best_key is None or key < best_key:
                best_key, best = key, [0, *combo]
    return best


def framings_for(n: int, prev: str | None) -> list[str]:
    seq = list(FRAMING_SEQ[n])
    if prev and seq[0] == prev:
        seq[0] = "medium_wide" if seq[0] == "wide" else "wide"
    return seq


def plan_scene(scene: Scene, cfg: dict[str, Any], prev_framing: str | None = None) -> list[PlannedShot]:
    """The shot plan for one image scene, from its narration segment timings."""
    lead = float(cfg["video"].get("scene_lead_in_sec", 0.0))
    pad = float(cfg["video"]["scene_padding_sec"])
    sc = cfg["shots"]
    lo, hi, mx = float(sc["min_shot_sec"]), float(sc["max_shot_sec"]), int(sc.get("max_per_scene", 3))
    cuts, end = _times(scene, lead, pad)
    starts = plan_cuts(cuts, end, lo, hi, mx)
    times = [0.0] + [cuts[j - 1] for j in starts[1:]] + [end]
    fr = framings_for(len(starts), prev_framing)
    return [PlannedShot(j, times[i], times[i + 1], fr[i]) for i, j in enumerate(starts)]


def plan_episode(ep: Episode, cfg: dict[str, Any]) -> dict[int, list[PlannedShot]]:
    """Plans for every image scene, in order (framing continuity runs across adjacent image scenes)."""
    out: dict[int, list[PlannedShot]] = {}
    prev: str | None = None
    for s in ep.scenes:
        if s.visual.type != "image":
            prev = None
            continue
        plan = plan_scene(s, cfg, prev)
        out[s.id] = plan
        prev = plan[-1].framing
    return out


def apply_plan(ep: Episode, cfg: dict[str, Any], scene_ids: list[int] | None, force: bool) -> list[str]:
    """Write the shot plan into image scenes that have no shots yet (all selected ones with force).
    Kept scenes still pass their last framing on, so framing never repeats across a kept scene."""
    from pipeline.schema import Shot
    notes: list[str] = []
    prev: str | None = None
    for s in ep.scenes:
        if s.visual.type != "image":
            prev = None
            continue
        chosen = scene_ids is None or s.id in scene_ids
        if not chosen or (s.visual.shots and not force):
            if chosen:
                notes.append(f"scene {s.id}: keeps its {len(s.visual.shots)} shot(s) (use --force to plan again)")
            prev = s.visual.shots[-1].framing if s.visual.shots else None
            continue
        plan = plan_scene(s, cfg, prev)
        s.visual.shots = [Shot(at_segment=p.at_segment, framing=p.framing) for p in plan]
        prev = plan[-1].framing
        notes.append(f"scene {s.id}: {len(plan)} shot(s) " +
                     ", ".join(f"[seg {p.at_segment}, {p.sec:.1f}s, {p.framing}]" for p in plan))
    return notes


def main(argv: list[str] | None = None) -> None:
    import argparse
    from pipeline.common import load_config, load_episode, resolve_episode_dir, save_episode, setup_logging, stage_timer
    from pipeline.schema import Status
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode")
    p.add_argument("--scene", type=int, action="append", dest="scenes")
    p.add_argument("--force", action="store_true", help="plan again and rewrite specs of the selected scenes")
    p.add_argument("--plan-only", action="store_true", help="shot plan by code only, no LLM")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    setup_logging(a.verbose)
    ep_dir = resolve_episode_dir(a.episode)
    cfg = load_config()
    with stage_timer(ep_dir, "shot plan" if a.plan_only else "shot specs") as run:
        ep = load_episode(ep_dir)
        if not ep.status.at_least(Status.narrated):
            raise SystemExit(f"status is {ep.status.value}; the shot plan needs narration timings (status narrated)")
        for n in apply_plan(ep, cfg, a.scenes, a.force):
            run.note(n)
        save_episode(ep_dir, ep)


if __name__ == "__main__":
    main()
