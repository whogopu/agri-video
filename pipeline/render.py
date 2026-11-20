"""Render an episode with Remotion.

    uv run python -m pipeline.render episodes/<id> --draft   # 540p → render/draft.mp4   (CHECKPOINT 2)
    uv run python -m pipeline.render episodes/<id>           # 1080p → render/video.mp4  (after draft approval)

Steps: validate at visuals_ready level → sync this episode's assets into
remotion/public/ (hard links, so no extra disk; other episodes' synced folders are
removed so the bundle stays small) → write render/props.json → npx remotion render.
Video: H.264 + AAC, 30 fps, VideoToolbox when available (config.yaml render.*).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from pipeline import audio
from pipeline.broll import LIBRARY, load_index
from pipeline.common import (
    REPO_ROOT, episode_frames, load_config, load_episode, resolve_episode_dir, setup_logging,
    stage_parser, stage_timer, write_json,
)
from pipeline.schema import Episode, Status
from pipeline.validate import validate

REMOTION = REPO_ROOT / "remotion"
PUBLIC = REMOTION / "public"
BRAND_LOGO = REPO_ROOT / "assets" / "brand" / "logo.png"


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.stat().st_ino == src.stat().st_ino:
            return
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def sync_assets(ep: Episode, ep_dir: Path) -> dict:
    """Mirror only what this episode uses into remotion/public. Returns the render props."""
    pub_eps = PUBLIC / "episodes"
    pub_eps.mkdir(parents=True, exist_ok=True)
    for d in pub_eps.iterdir():  # keep the bundle small: one episode at a time
        if d.name != ep.id:
            shutil.rmtree(d) if d.is_dir() else d.unlink()
    dst_root = pub_eps / ep.id
    if dst_root.exists():
        shutil.rmtree(dst_root)

    for s in ep.scenes:
        if s.audio:
            link_or_copy(ep_dir / s.audio.file, dst_root / s.audio.file)
        for f in s.image_files():
            link_or_copy(ep_dir / f, dst_root / f)

    broll_files: dict[str, str] = {}
    used = {s.visual.broll_id for s in ep.scenes if s.visual.type == "broll" and s.visual.broll_id}
    if used:
        index = {c["id"]: c for c in load_index(LIBRARY)["clips"]}
        for bid in used:
            f = index[bid]["file"]
            link_or_copy(LIBRARY / "clips" / f, PUBLIC / "broll" / f)
            broll_files[bid] = f

    room_tone = None  # one continuous track under the whole video (pipeline.narration writes it)
    if (ep_dir / "audio" / "room-tone.wav").exists():
        link_or_copy(ep_dir / "audio" / "room-tone.wav", dst_root / "audio" / "room-tone.wav")
        room_tone = f"episodes/{ep.id}/audio/room-tone.wav"

    logo = None
    if BRAND_LOGO.exists():
        link_or_copy(BRAND_LOGO, PUBLIC / "brand" / "logo.png")
        logo = "brand/logo.png"

    return {"assetBase": f"episodes/{ep.id}", "brollBase": "broll", "brollFiles": broll_files, "logo": logo,
            "roomTone": room_tone}


def caption_font_size(cfg: dict, fmt: str) -> int | None:
    """config captions.font_size_px: a number, or {long: .., short: ..}. None → Remotion theme default."""
    v = cfg.get("captions", {}).get("font_size_px")
    if isinstance(v, dict):
        v = v.get(fmt)
    return int(v) if v else None


def remotion_render(props_path: Path, out: Path, rcfg: dict, scale: float | None) -> None:
    cmd = ["npx", "remotion", "render", "src/index.ts", "Episode", str(out),
           f"--props={props_path}", f"--concurrency={rcfg['concurrency']}",
           f"--hardware-acceleration={rcfg['hardware_acceleration']}", "--codec=h264", "--audio-codec=aac"]
    if scale:
        cmd.append(f"--scale={scale}")
    res = subprocess.run(cmd, cwd=REMOTION)
    if res.returncode != 0:
        raise RuntimeError(f"remotion render failed (exit {res.returncode})")


def main() -> None:
    p = stage_parser(__doc__)
    p.add_argument("--draft", action="store_true", help="540p review render → render/draft.mp4")
    p.add_argument("--allow-unapproved", action="store_true", help="testing only: skip the status gate")
    args = p.parse_args()
    setup_logging(args.verbose)
    ep_dir = resolve_episode_dir(args.episode)
    cfg = load_config()
    rcfg = cfg["render"]

    with stage_timer(ep_dir, "render (draft)" if args.draft else "render (final)") as run:
        ep = load_episode(ep_dir)
        need = Status.visuals_ready if args.draft else Status.draft_rendered
        if not ep.status.at_least(need) and not args.allow_unapproved:
            raise SystemExit(f"status is {ep.status.value}; {'draft' if args.draft else 'final'} render needs "
                             f"{need.value}" + ("" if args.draft else " (draft reviewed at checkpoint 2)"))
        rep, _ = validate(ep_dir, Status.visuals_ready)
        if not rep.ok:
            print(rep.render())
            raise SystemExit("episode is not ready to render (see errors above)")

        out = ep_dir / "render" / ("draft.mp4" if args.draft else "video.mp4")
        if out.exists() and not args.force and out.stat().st_mtime > (ep_dir / "episode.json").stat().st_mtime:
            run.note(f"{out.name} is newer than episode.json; skipping (use --force to re-render)")
            return

        props = {"episode": ep.model_dump(mode="json"), "paddingSec": cfg["video"]["scene_padding_sec"],
                 "leadInSec": float(cfg["video"].get("scene_lead_in_sec", 0.0)),
                 "captionFontSize": caption_font_size(cfg, ep.format), **sync_assets(ep, ep_dir)}
        props_path = ep_dir / "render" / "props.json"
        write_json(props_path, props)

        expected = episode_frames(ep, cfg) / ep.video.fps
        scale = rcfg["draft_scale"] if args.draft else None
        run.note(f"rendering {out.name}: {ep.video.width}x{ep.video.height}"
                 + (f" × {scale}" if scale else "") + f", expected {expected:.2f}s")
        remotion_render(props_path, out, rcfg, scale)

        got = audio.duration(out)
        run.note(f"{out.relative_to(REPO_ROOT)}: {got:.2f}s ({out.stat().st_size / 1e6:.1f} MB)")
        if abs(got - expected) > 0.15:
            run.note(f"WARNING duration differs from expected by {got - expected:+.2f}s")
    print(f"\nRendered: {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
