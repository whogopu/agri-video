"""Shot specs stage: plan the shots of every image scene in code, then let a local LLM write each shot's spec.

    uv run python -m pipeline.shot_specs episodes/<id> [--scene N] [--force]       # plan shots + write specs
    uv run python -m pipeline.shot_specs episodes/<id> --plan-only                 # shot plan by code, no LLM
    uv run python -m pipeline.shot_specs episodes/<id> --review                    # rewrite review/shots.md only
    uv run python -m pipeline.shot_specs episodes/<id> --scene N --shot K --revise "user note"   # rewrite one spec
    uv run python -m pipeline.shot_specs episodes/<id> --scene N --shot K --revise               # from its failed inspection
    uv run python -m pipeline.shot_specs episodes/<id> --scene N --shot K --approve              # user approves a 2nd revision

Checkpoint (status shots_approved, between narrated and visuals_ready): the stage writes review/shots.md with
every shot's timing, Hindi sentence, framing, a summary and the full rendered prompt; the dashboard shows the
same. The user approves with `validate --set-status shots_approved`; pipeline.images refuses episode shots
before that.

The spec writer is pipeline/spec_writer.py (local LLM via the vlm/ env, pipeline/local_llm.py). Every LLM
answer is appended to review/shot_specs_llm.jsonl.

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
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.common import save_episode

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


SENT_SPLIT = re.compile(r"(?<=[।?!])\s+")


def scene_sentences(scene: Scene) -> list[str]:
    """Display sentences of a scene, split like visual_rules.shot_sentence (markup removed)."""
    text = re.sub(r"\{[a-z]+\}|\|+", "", scene.narration_display).strip()
    return [p.strip() for p in SENT_SPLIT.split(text) if p.strip()]


def cast_info(ep: Episode) -> list[dict[str, str]]:
    from pipeline.cast import load_character
    out = []
    for cid in ep.cast:
        c = load_character(cid)
        out.append({"id": c.id, "gender": "man" if c.gender == "male" else "woman", "role": c.role})
    return out


def shot_context(ep: Episode, scene: Scene, k: int, cfg: dict[str, Any], cast: list[dict[str, str]]):
    """Everything the spec writer gets for shot k (1-based) of an image scene."""
    from pipeline.spec_writer import ShotContext
    shots = scene.visual.shots
    sh = shots[k - 1]
    parts = scene_sentences(scene)
    a = sh.at_segment
    b = shots[k].at_segment if k < len(shots) else len(parts)
    sentence = " ".join(parts[a:b]) or " ".join(parts)
    idx = [s.id for s in ep.scenes].index(scene.id)
    before = parts[a - 1] if a > 0 else (scene_sentences(ep.scenes[idx - 1])[-1:] or [""])[0] if idx > 0 else ""
    after = parts[b] if b < len(parts) else (
        (scene_sentences(ep.scenes[idx + 1])[:1] or [""])[0] if idx + 1 < len(ep.scenes) else "")
    others = []
    for j, o in enumerate(shots, 1):
        if j != k:
            oe = shots[j].at_segment if j < len(shots) else len(parts)
            others.append(" ".join(parts[o.at_segment:oe]))
    framings = cfg["shot_specs"]["framings"]
    framing = framings.get(sh.framing or "", framings["medium_wide"])
    return ShotContext(key=f"s{scene.id}-k{k}", sentence=sentence, framing=framing, topic=ep.title_hi,
                       purpose=scene.purpose, before=before, after=after, other_shots=others, cast=cast)


def spec_targets(ep: Episode, scene_ids: list[int] | None, force: bool) -> list[tuple[Scene, int, Any]]:
    """Shots that need a spec: no spec and no image_prompt (with force: every shot of the selected scenes)."""
    out = []
    for s in ep.scenes:
        if s.visual.type != "image" or (scene_ids and s.id not in scene_ids):
            continue
        for k, sh in enumerate(s.visual.shots, 1):
            if force or not (sh.spec or sh.image_prompt):
                out.append((s, k, sh))
    return out


def model_label(model: str) -> str:
    return "llm:" + model.split("/")[-1]


def apply_result(sh: Any, r: Any, model: str) -> None:
    """Write a spec result into a shot (a flagged result keeps its last spec and lists its flags)."""
    from pipeline.schema import SpecInfo
    from pipeline.scene_spec import cast_ids
    old = sh.spec_info or SpecInfo()
    sh.image_prompt = None
    sh.spec = r.spec
    sh.characters = cast_ids(r.spec) if r.spec else []
    sh.spec_info = SpecInfo(writer=model_label(model), rounds=r.rounds, flags=list(r.errors),
                            warnings=list(r.warnings), revisions=old.revisions,
                            revised_because=old.revised_because, needs_approval=old.needs_approval)


def write_episode_specs(ep_dir: Path, ep: Episode, targets: list, cfg: dict[str, Any], run, llm=None) -> list[str]:
    """Run the spec writer over the target shots and save them into the episode. Returns flagged shots."""
    from pipeline.spec_writer import write_specs
    if not targets:
        return []
    cast = cast_info(ep)
    ctxs = {}
    for s, k, sh in targets:
        c = shot_context(ep, s, k, cfg, cast)
        ctxs[c.key] = (c, sh)
    log = ep_dir / "review" / "shot_specs_llm.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    model = cfg["shot_specs"]["model"]
    results = write_specs([c for c, _ in ctxs.values()], cfg, llm=llm, log=log, progress=run.note)
    flagged = []
    for key, (c, sh) in ctxs.items():
        r = results[key]
        apply_result(sh, r, model)
        tag = key.replace("s", "scene ", 1).replace("-k", " shot ")
        if r.ok:
            run.note(f"{tag}: spec ok after {r.rounds} repair round(s), {r.sec:.0f}s"
                     + (f"; warnings: {'; '.join(r.warnings)}" if r.warnings else ""))
        else:
            flagged.append(tag)
            run.note(f"**FLAG** {tag}: spec still failing after {r.rounds} repair round(s), needs Claude/user: "
                     + "; ".join(r.errors))
    save_episode(ep_dir, ep)
    return flagged


def revise_shot(ep_dir: Path, ep: Episode, scene_id: int, k: int, note: str | None, cfg: dict[str, Any], run,
                llm=None) -> bool:
    """Rewrite one shot's spec with the LLM. With a note: the user's change (no re-approval needed, the user
    asked for it). Without: the shot's failed-inspection notes; the first such automatic revision goes straight
    to `images --retry`, from the second on the shot waits for `--approve` (user decision 2026-11-22).
    Returns True when the new spec passes the checks."""
    from pipeline.spec_writer import write_specs
    s = ep.scene(scene_id)
    if s.visual.type != "image" or not 1 <= k <= len(s.visual.shots):
        raise SystemExit(f"scene {scene_id} has no image shot {k}")
    sh = s.visual.shots[k - 1]
    auto = not (note or "").strip()
    if auto:
        if not sh.inspection or sh.inspection.passed:
            raise SystemExit(f"scene {scene_id} shot {k} has no failed inspection to revise from; "
                             f"give a note: --revise \"what to change\"")
        note = f"the generated image failed inspection: {sh.inspection.notes}"
    ctx = shot_context(ep, s, k, cfg, cast_info(ep))
    ctx.old_spec, ctx.note = sh.spec, note
    if not sh.spec and sh.image_prompt:
        ctx.note += f" (the shot so far had this free-text prompt: {sh.image_prompt})"
    log = ep_dir / "review" / "shot_specs_llm.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    r = write_specs([ctx], cfg, llm=llm, log=log, progress=run.note)[ctx.key]
    apply_result(sh, r, cfg["shot_specs"]["model"])
    info = sh.spec_info
    info.revised_because = ("inspection: " if auto else "user note: ") + (sh.inspection.notes if auto else note)
    if auto:
        info.revisions += 1
        info.needs_approval = info.revisions >= 2
    save_episode(ep_dir, ep)
    tag = f"scene {scene_id} shot {k}"
    if not r.ok:
        run.note(f"**FLAG** {tag}: revised spec still failing after {r.rounds} repair round(s): " + "; ".join(r.errors))
    elif auto and info.needs_approval:
        run.note(f"{tag}: spec revised after inspection (revision {info.revisions}); **waits for the user's "
                 f"approval** before images --retry")
    elif auto:
        run.note(f"{tag}: spec revised after inspection (revision {info.revisions}); next: images --scene "
                 f"{scene_id} --shot {k} --retry")
    else:
        run.note(f"{tag}: spec revised with the user's note: {note}")
    return r.ok


def approve_shot(ep_dir: Path, ep: Episode, scene_id: int, k: int, run) -> None:
    """The user approved a shot whose spec was revised a second time after failed inspections."""
    s = ep.scene(scene_id)
    if s.visual.type != "image" or not 1 <= k <= len(s.visual.shots):
        raise SystemExit(f"scene {scene_id} has no image shot {k}")
    info = s.visual.shots[k - 1].spec_info
    if not info or not info.needs_approval:
        raise SystemExit(f"scene {scene_id} shot {k} is not waiting for approval")
    if info.flags:
        raise SystemExit(f"scene {scene_id} shot {k}: its spec still fails checks; fix it first: {'; '.join(info.flags)}")
    info.needs_approval = False
    save_episode(ep_dir, ep)
    run.note(f"scene {scene_id} shot {k}: the user approved revision {info.revisions}")


def shot_times(scene: Scene, cfg: dict[str, Any]) -> list[tuple[float, float]]:
    """(start, end) on screen of every shot, seconds from the scene start (as the render places them)."""
    from pipeline.common import shot_starts_sec
    lead = float(cfg["video"].get("scene_lead_in_sec", 0.0))
    end = lead + (scene.audio.duration_sec if scene.audio else 0.0) + float(cfg["video"]["scene_padding_sec"])
    starts = shot_starts_sec(scene, lead)
    return list(zip(starts, starts[1:] + [end]))


def shot_summary(sh: Any) -> list[str]:
    """Short lines for the checkpoint: what it teaches, who does what with each hand, objects, flows."""
    if not sh.spec:
        return [f"free-text prompt: {(sh.image_prompt or '')[:200]}"] if sh.image_prompt else []
    s = sh.spec
    out = [f"**Teaches:** {s.get('teaches', '')}"]
    if s.get("crop_stage"):
        out.append(f"**Field:** {s['crop_stage']}")
    for p in s.get("people") or []:
        who = f"{p['cast']} (cast)" if p.get("cast") else f"{p.get('role', 'person')}, {p.get('gender', '?')}"
        hands = "; ".join(f"{side.split('_')[0]} hand: {(p.get(side) or {}).get('grip', '?')}"
                          for side in ("left_hand", "right_hand"))
        out.append(f"**{who}:** {p.get('posture', '')}. {hands}")
    objs = [f"{o.get('name')} ({o.get('support', '?')})" for o in s.get("objects") or []]
    if objs:
        out.append("**Objects:** " + "; ".join(objs))
    for f in s.get("flows") or []:
        out.append(f"**Flow:** {f.get('material')} ← {f.get('source')} → {f.get('landing')}")
    return out


def write_review(ep_dir: Path, ep: Episode, cfg: dict[str, Any]) -> Path:
    """review/shots.md: the shot-plan checkpoint, per shot timing, sentence, framing, summary, full prompt."""
    from pipeline.images import render_shot_prompt
    rel = f"episodes/{ep_dir.name}"
    scenes = [s for s in ep.scenes if s.visual.type == "image"]
    n_shots = sum(len(s.visual.shots) for s in scenes)
    body: list[str] = []
    n_flag = n_rev = n_wait = 0
    for s in scenes:
        parts = scene_sentences(s)
        body.append(f"\n## Scene {s.id} · {s.purpose} · {len(s.visual.shots)} shot(s)\n")
        times = shot_times(s, cfg)
        for k, sh in enumerate(s.visual.shots, 1):
            a, b = times[k - 1]
            nxt = s.visual.shots[k].at_segment if k < len(s.visual.shots) else len(parts)
            sentence = " ".join(parts[sh.at_segment:nxt]) or " ".join(parts)
            info = sh.spec_info
            marks = []
            if info and info.flags:
                marks.append("**FLAGGED: needs Claude/user**")
                n_flag += 1
            if info and info.revisions:
                marks.append(f"revised after inspection ×{info.revisions}")
                n_rev += 1
            if info and info.needs_approval:
                marks.append("**waits for your approval**")
                n_wait += 1
            if sh.inspection:
                marks.append("image passed" if sh.inspection.passed else "image FAILED inspection")
            body.append(f"### Shot {s.id}.{k} · {a:.1f}–{b:.1f} s ({b - a:.1f} s) · {sh.framing or 'framing ?'}"
                        + (" · " + " · ".join(marks) if marks else ""))
            body.append(f"\n> {sentence}\n")
            body += [f"- {line}" for line in shot_summary(sh)]
            if info:
                body.append(f"- Written by {info.writer or '?'}" + (f", {info.rounds} repair round(s)" if info.rounds else ""))
                if info.revised_because:
                    body.append(f"- Last revision because: {info.revised_because}")
                for fl in info.flags:
                    body.append(f"- ⚠ flag: {fl}")
            prompt, errors, warnings = render_shot_prompt(ep, sh, cfg["images"], f"shot {s.id}.{k}")
            for w in (info.warnings if info else []) or warnings:
                body.append(f"- warning: {w}")
            for e in errors:
                body.append(f"- ⚠ error: {e}")
            if prompt:
                body.append(f"\nPrompt ({len(prompt.split())} words):\n\n```text\n{prompt}\n```\n")
            else:
                body.append("")
    head = [f"# Shot plan: {ep.title_hi or ep.id}", "",
            f"Status `{ep.status.value}` · {len(scenes)} image scenes · {n_shots} shots · {n_flag} flagged · "
            f"{n_rev} revised · {n_wait} waiting for approval", "",
            "**Checkpoint: shot plan.** Read each shot: is it what the sentence says, right crop stage, right "
            "people, every hand doing something sensible? Nothing is generated until you approve.", "",
            f"- Change a shot: `uv run python -m pipeline.shot_specs {rel} --scene N --shot K --revise \"your note\"`",
            f"- Approve the plan: `uv run python -m pipeline.validate {rel} --set-status shots_approved`",
            f"- Approve one re-revised shot: `uv run python -m pipeline.shot_specs {rel} --scene N --shot K --approve`",
            "", "Timings are seconds from the scene start, as rendered (lead-in included)."]
    out = ep_dir / "review" / "shots.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(head + body).rstrip() + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse
    from pipeline.common import load_config, load_episode, resolve_episode_dir, setup_logging, stage_timer
    from pipeline.schema import Status
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode")
    p.add_argument("--scene", type=int, action="append", dest="scenes")
    p.add_argument("--force", action="store_true", help="plan again and rewrite specs of the selected scenes")
    p.add_argument("--plan-only", action="store_true", help="shot plan by code only, no LLM")
    p.add_argument("--review", action="store_true", help="only rewrite review/shots.md")
    p.add_argument("--shot", type=int, help="with --revise/--approve: shot number within the scene (1-based)")
    p.add_argument("--revise", nargs="?", const="", metavar="NOTE",
                   help="rewrite one shot's spec: with the user's NOTE, or from its failed inspection")
    p.add_argument("--approve", action="store_true",
                   help="the user approves one shot that waits after a second automatic revision")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    setup_logging(a.verbose)
    ep_dir = resolve_episode_dir(a.episode)
    cfg = load_config()
    if a.review:
        print(write_review(ep_dir, load_episode(ep_dir), cfg))
        return
    if a.revise is not None or a.approve:
        if not (a.scenes and len(a.scenes) == 1 and a.shot):
            p.error("--revise/--approve need one --scene N and --shot K")
        with stage_timer(ep_dir, "shot specs (approve)" if a.approve else "shot specs (revise)") as run:
            ep = load_episode(ep_dir)
            if a.approve:
                approve_shot(ep_dir, ep, a.scenes[0], a.shot, run)
            else:
                revise_shot(ep_dir, ep, a.scenes[0], a.shot, a.revise, cfg, run)
            run.note(f"checkpoint page: {write_review(ep_dir, ep, cfg).relative_to(ep_dir)}")
        return
    with stage_timer(ep_dir, "shot plan" if a.plan_only else "shot specs") as run:
        ep = load_episode(ep_dir)
        if not ep.status.at_least(Status.narrated):
            raise SystemExit(f"status is {ep.status.value}; the shot plan needs narration timings (status narrated)")
        for n in apply_plan(ep, cfg, a.scenes, a.force):
            run.note(n)
        save_episode(ep_dir, ep)
        if not a.plan_only:
            flagged = write_episode_specs(ep_dir, ep, spec_targets(ep, a.scenes, a.force), cfg, run)
        else:
            flagged = []
        out = write_review(ep_dir, ep, cfg)
        run.note(f"checkpoint page: {out.relative_to(ep_dir)}")
    if flagged:
        print(f"Flagged (spec still failing, needs Claude/user): {', '.join(flagged)}", file=sys.stderr)


if __name__ == "__main__":
    main()
