"""Review stage: contact sheets + automated checks → review/review.md for Claude to complete.

    uv run python -m pipeline.review episodes/<id> [--draft]

- Contact sheets: a frame every `review.frame_interval_sec` seconds, `frames_per_sheet` per
  sheet, each stamped with its time (Pillow; Homebrew ffmpeg has no drawtext).
- Checks: duration vs. sum of scenes, integrated loudness + true peak, black frames,
  long static stretches (info only: graphics legitimately hold still).
- review.md lists the scene start times (to map a timestamp to a scene) and the manual
  checklist, which Claude fills in after LOOKING at every sheet.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline import audio
from pipeline.common import (
    REPO_ROOT, episode_frames, load_config, load_episode, resolve_episode_dir, scene_frames,
    setup_logging, stage_parser, stage_timer, write_json,
)
from pipeline.schema import Episode

MANUAL_CHECKS = [
    "Devanagari renders correctly (no broken conjuncts, no dotted circles ◌)",
    "Captions readable, max 2 lines, inside safe margins",
    "Text never covers the key part of an image",
    "Visuals match the narration",
    "No black or frozen frames (beyond intentional graphic holds)",
    "Watermark present throughout",
    "Indian rural context everywhere; no garbled text inside images",
    "People: 2 arms/hands/legs each, 5 fingers per visible hand, natural posture, correct dress, tools held correctly (config images.inspection_checklist)",
]


def fmt_t(sec: float) -> str:
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


def extract_frames(video: Path, interval: float, out_dir: Path, width: int) -> list[tuple[float, Path]]:
    pattern = out_dir / "f%05d.png"
    sel = f"isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval})"
    audio.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
               f"select='{sel}',scale={width}:-2,showinfo", "-fps_mode", "vfr", str(pattern)])
    # showinfo isn't captured by run(); timestamps are i*interval by construction of the select
    frames = sorted(out_dir.glob("f*.png"))
    return [(i * interval, f) for i, f in enumerate(frames)]


def make_sheets(frames: list[tuple[float, Path]], per_sheet: int, cols: int, out_dir: Path) -> list[Path]:
    font = ImageFont.load_default(size=26)
    sheets = []
    for n, start in enumerate(range(0, len(frames), per_sheet), 1):
        batch = frames[start:start + per_sheet]
        w, h = Image.open(batch[0][1]).size
        rows = -(-len(batch) // cols)
        gap = 6
        sheet = Image.new("RGB", (cols * w + (cols + 1) * gap, rows * h + (rows + 1) * gap), "white")
        for i, (t, f) in enumerate(batch):
            im = Image.open(f).convert("RGB")
            d = ImageDraw.Draw(im)
            label = fmt_t(t)
            box = d.textbbox((0, 0), label, font=font)
            bw, bh = box[2] + 16, box[3] + 12
            # bottom-left: keeps the on-screen tag (top-left), watermark (top-right) and captions visible
            d.rectangle((0, im.height - bh, bw, im.height), fill=(0, 0, 0))
            d.text((8, im.height - bh + 4), label, fill=(255, 220, 0), font=font)
            x, y = gap + (i % cols) * (w + gap), gap + (i // cols) * (h + gap)
            sheet.paste(im, (x, y))
        path = out_dir / f"sheet-{n:02d}.png"
        sheet.save(path)
        sheets.append(path)
    return sheets


def detect_issues(video: Path) -> dict[str, list]:
    res = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf",
                          "scale=320:-2,blackdetect=d=0.3:pix_th=0.10,freezedetect=n=0.002:d=4",
                          "-f", "null", "-"], capture_output=True, text=True)
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", res.stderr)]
    fstart = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", res.stderr)]
    fdur = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", res.stderr)]
    return {"black": black, "static": list(zip(fstart, fdur))}


def scene_starts(ep: Episode, cfg: dict) -> list[tuple[int, float, str]]:
    fps, pad, xf = ep.video.fps, float(cfg["video"]["scene_padding_sec"]), int(cfg["render"]["crossfade_frames"])
    lead = float(cfg["video"].get("scene_lead_in_sec", 0.0))
    out, f = [], 0
    for s in ep.scenes:
        out.append((s.id, f / fps, s.visual.type or "?"))
        f += scene_frames(s.audio.duration_sec if s.audio else None, fps, pad, xf, lead) - xf
    return out


def main() -> None:
    p = stage_parser(__doc__)
    p.add_argument("--draft", action="store_true", help="review render/draft.mp4 instead of video.mp4")
    args = p.parse_args()
    setup_logging(args.verbose)
    ep_dir = resolve_episode_dir(args.episode)
    cfg = load_config()
    rcfg = cfg["review"]

    with stage_timer(ep_dir, "review") as run:
        ep = load_episode(ep_dir)
        video = ep_dir / "render" / ("draft.mp4" if args.draft else "video.mp4")
        if not video.exists():
            raise SystemExit(f"{video} not found; render first")
        out_dir = ep_dir / "review"
        out_dir.mkdir(exist_ok=True)
        for old in out_dir.glob("sheet-*.png"):
            old.unlink()

        portrait = ep.video.height > ep.video.width
        with tempfile.TemporaryDirectory() as tmp:
            frames = extract_frames(video, float(rcfg["frame_interval_sec"]), Path(tmp), 300 if portrait else 480)
            sheets = make_sheets(frames, int(rcfg["frames_per_sheet"]), 6 if portrait else 4, out_dir)

        dur = audio.duration(video)
        expected = episode_frames(ep, cfg) / ep.video.fps
        loud = audio.measure_loudness([video])
        issues = detect_issues(video)
        target, ceiling = cfg["audio"]["target_lufs"], cfg["audio"]["true_peak_db"]
        checks = {
            "video": str(video.relative_to(ep_dir)),
            "duration_sec": round(dur, 2), "expected_sec": round(expected, 2),
            "duration_ok": abs(dur - expected) <= 0.15,
            "lufs": loud["lufs"], "true_peak": loud["true_peak"],
            "loudness_ok": abs(loud["lufs"] - target) <= 1.0 and loud["true_peak"] <= ceiling + 0.5,
            "black_segments": issues["black"], "static_segments": issues["static"],
            "sheets": [s.name for s in sheets],
        }
        write_json(out_dir / "checks.json", checks)

        ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
        lines = [
            f"# Review — {ep.id}", "",
            f"Video: `{checks['video']}` · {ep.video.width}x{ep.video.height} · {ep.format}", "",
            "## Automated checks", "",
            "| Check | Result | Details |", "|---|---|---|",
            f"| Duration | {ok(checks['duration_ok'])} | {dur:.2f}s (expected {expected:.2f}s from scenes) |",
            f"| Loudness | {ok(checks['loudness_ok'])} | {loud['lufs']:.1f} LUFS (target {target}), true peak {loud['true_peak']:.1f} dBTP (ceiling {ceiling}) |",
            f"| Black frames | {ok(not issues['black'])} | "
            + (", ".join(f"{fmt_t(a)}–{fmt_t(b)}" for a, b in issues["black"]) or "none") + " |",
            "| Static stretches ≥4 s | info | "
            + (", ".join(f"{fmt_t(a)} ({d:.1f}s)" for a, d in issues["static"]) or "none")
            + " — fine on graphic holds, a problem on image/B-roll scenes |",
            "", "## Scene starts", "",
            " · ".join(f"{sid}: {fmt_t(t)} ({vt})" for sid, t, vt in scene_starts(ep, cfg)),
            "", "## Contact sheets", "", *[f"- `review/{s.name}`" for s in sheets],
            "", "## Manual checks (Claude: look at every sheet, then fill in)", "",
            "| Check | Result | Timestamps / notes |", "|---|---|---|",
            *[f"| {c} | TODO | |" for c in MANUAL_CHECKS],
            "", "## Verdict", "", "TODO", "",
        ]
        (out_dir / "review.md").write_text("\n".join(lines), encoding="utf-8")
        run.note(f"{len(sheets)} sheet(s) from {len(frames)} frames; duration {ok(checks['duration_ok'])}, "
                 f"loudness {loud['lufs']:.1f} LUFS, black segments {len(issues['black'])}")
    print(f"Wrote {ep_dir.relative_to(REPO_ROOT)}/review/review.md and {len(sheets)} contact sheet(s). "
          "Look at every sheet and fill in the manual checks.")


if __name__ == "__main__":
    main()
