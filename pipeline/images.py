"""Image stage: generate a still for every scene whose visual.type is "image".

    uv run python -m pipeline.images episodes/<id> [--scene N] [--force]
    uv run python -m pipeline.images episodes/<id> --scene N --retry [--prompt "..."]   # new seed, next attempt
    uv run python -m pipeline.images --prompt "..." --format short --out x.png [--seed 7]  # one-off test
    uv run python -m pipeline.images episodes/<id> --scene N --crops            # zoomed quarters for inspection
    uv run python -m pipeline.images episodes/<id> --scene N --inspect pass --notes "farmer: 2 arms, 2 hands (5 fingers), 2 legs; spade single handle"
    uv run python -m pipeline.images episodes/<id> --scene N --use-attempt 1 [--seed S --prompt "..."]  # go back to an earlier attempt
    uv run python -m pipeline.images --checklist                                # print the inspection checklist

Every image must be inspected against config.yaml images.inspection_checklist (anatomy,
posture, dress, tool handling, text) and the result recorded with --inspect. The record
stores the image's SHA-1, so regenerating an image clears it; validate blocks
visuals_ready until every image scene has a passing inspection of its current file.

Size comes from config.yaml formats.<format>.image_size (16:9 or 9:16). The style suffix from
config.yaml is appended to every prompt. Every attempt is kept as images/scene-XX-aN.png; the
current pick is copied to images/scene-XX.png (episode.json image_file). After
images.max_attempts attempts the scene is flagged in log.md for the user instead.

Backend contract: generate(prompt, seed, width, height, out_path) -> seconds.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from pipeline.schema import ImageInspection
from pipeline.common import (
    REPO_ROOT, append_log, format_config, load_config, load_episode, log, resolve_episode_dir,
    save_episode, selected_scenes, setup_logging, stage_timer,
)


class MfluxBackend:
    """mflux CLI (MLX) installed as a uv tool. One process per image; peak ~3.7 GB for klein-4B q4."""

    def __init__(self, icfg: dict[str, Any]):
        self.cfg = icfg

    def generate(self, prompt: str, seed: int, width: int, height: int, out_path: Path) -> float:
        c = self.cfg
        cmd = [c.get("command", "mflux-generate"), "--model", c["model"],
               "--prompt", prompt, "--seed", str(seed), "--width", str(width), "--height", str(height),
               "--steps", str(c["steps"]), "--output", str(out_path)]
        if c.get("base_model"):
            cmd += ["--base-model", c["base_model"]]
        if c.get("guidance") is not None:
            cmd += ["--guidance", str(c["guidance"])]
        if c.get("quantize"):
            cmd += ["--quantize", str(c["quantize"])]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"mflux failed ({res.returncode}): {res.stderr[-1500:]}")
        return time.monotonic() - t0


BACKENDS = {"mflux": MfluxBackend}


def get_backend(icfg: dict[str, Any]):
    try:
        return BACKENDS[icfg["backend"]](icfg)
    except KeyError:
        raise SystemExit(f"unknown images backend {icfg['backend']!r}; available: {', '.join(BACKENDS)}")


def full_prompt(prompt: str, icfg: dict[str, Any]) -> str:
    suffix = icfg.get("style_suffix", "").strip()
    return f"{prompt.rstrip(' .,')}, {suffix}" if suffix else prompt


def file_sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def checklist_text(icfg: dict[str, Any]) -> str:
    items = icfg.get("inspection_checklist", [])
    return "\n".join(f"  [ ] {i}" for i in items)


def write_crops(image: Path, out_dir: Path) -> list[Path]:
    """4 overlapping quarters, each upscaled 2× — extra limbs and fused fingers show up here."""
    out_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(image).convert("RGB")
    w, h = im.size
    cw, ch = int(w * 0.6), int(h * 0.6)
    boxes = {"tl": (0, 0), "tr": (w - cw, 0), "bl": (0, h - ch), "br": (w - cw, h - ch)}
    out = []
    for name, (x, y) in boxes.items():
        p = out_dir / f"{image.stem}-{name}.png"
        im.crop((x, y, x + cw, y + ch)).resize((cw * 2, ch * 2), Image.LANCZOS).save(p)
        out.append(p)
    return out


def default_seed(episode_id: str, scene_id: int, attempt: int) -> int:
    """Deterministic per episode/scene/attempt, so reruns reproduce and retries differ."""
    h = hashlib.sha1(f"{episode_id}:{scene_id}:{attempt}".encode()).hexdigest()
    return int(h[:8], 16) % 1_000_000


def run_episode(args: argparse.Namespace) -> None:
    ep_dir = resolve_episode_dir(args.episode)
    cfg = load_config()
    icfg = cfg["images"]
    with stage_timer(ep_dir, "images") as run:
        ep = load_episode(ep_dir)
        width, height = format_config(cfg, ep.format)["image_size"]
        backend = get_backend(icfg)
        max_attempts = int(icfg.get("max_attempts", 3))
        scenes = [s for s in selected_scenes(ep, args.scenes) if s.visual.type == "image"]
        if not scenes:
            run.note("no image scenes selected")
        flagged = []
        for s in scenes:
            v = s.visual
            if args.prompt:
                v.image_prompt = args.prompt
            if not v.image_prompt:
                raise SystemExit(f"scene {s.id}: no image_prompt")
            final = ep_dir / "images" / f"scene-{s.id:02d}.png"
            if final.exists() and not (args.force or args.retry):
                continue
            if args.retry or v.attempts == 0:
                attempt = v.attempts + 1
            else:
                attempt = v.attempts  # --force: redo the current attempt with the same seed
            if attempt > max_attempts and not args.extra_attempt:
                msg = (f"scene {s.id}: reached {max_attempts} image attempts; needs a human decision "
                       f"(B-roll, graphic, or a different idea)")
                append_log(ep_dir, f"\n**FLAG** {msg}")
                flagged.append(s.id)
                continue
            seed = args.seed if args.seed is not None else (
                v.seed if (v.seed is not None and not args.retry) else default_seed(ep.id, s.id, attempt))
            attempt_file = ep_dir / "images" / f"scene-{s.id:02d}-a{attempt}.png"
            secs = backend.generate(full_prompt(v.image_prompt, icfg), seed, width, height, attempt_file)
            shutil.copyfile(attempt_file, final)
            v.seed, v.attempts = seed, attempt
            v.inspection = None  # new pixels → must be inspected again
            s.image_file = f"images/{final.name}"
            save_episode(ep_dir, ep)  # save after each image so a crash keeps finished work
            run.note(f"scene {s.id}: attempt {attempt}, seed {seed}, {width}x{height}, {secs:.1f}s → {attempt_file.name}")
        if flagged:
            print(f"Flagged for the user (max attempts reached): scenes {flagged}", file=sys.stderr)
    print("Inspect EVERY image at full size, plus zoomed crops (--crops), person by person, against:")
    print(checklist_text(icfg))
    print("Then record each result:  --scene N --inspect pass|fail --notes \"<per-person counts>\"")
    for s in scenes:
        if s.image_file:
            print(f"  {ep_dir.name}/{s.image_file}  (scene {s.id}: {s.narration_display[:60]})")


def run_inspection_tools(args: argparse.Namespace) -> None:
    ep_dir = resolve_episode_dir(args.episode)
    icfg = load_config()["images"]
    ep = load_episode(ep_dir)
    scenes = [s for s in selected_scenes(ep, args.scenes) if s.visual.type == "image" and s.image_file]
    if not scenes:
        raise SystemExit("no generated image scenes selected")
    if args.use_attempt:
        with stage_timer(ep_dir, "images (use earlier attempt)") as run:
            for s in scenes:
                src = ep_dir / "images" / f"scene-{s.id:02d}-a{args.use_attempt}.png"
                if not src.exists():
                    raise SystemExit(f"{src.name} not found")
                shutil.copyfile(src, ep_dir / s.image_file)
                if args.seed is not None:
                    s.visual.seed = args.seed
                if args.prompt:
                    s.visual.image_prompt = args.prompt
                s.visual.inspection = None  # different pixels → inspect again
                run.note(f"scene {s.id}: now using {src.name} (seed {s.visual.seed})")
            save_episode(ep_dir, ep)
        return
    if args.crops:
        for s in scenes:
            for c in write_crops(ep_dir / s.image_file, ep_dir / "images" / "inspect"):
                print(c.relative_to(REPO_ROOT))
        return
    passed = args.inspect == "pass"
    if passed and not (args.notes or "").strip():
        raise SystemExit("--inspect pass needs --notes with what you counted (arms, hands, fingers, legs per person; tools)")
    with stage_timer(ep_dir, "image inspection") as run:
        for s in scenes:
            img = ep_dir / s.image_file
            s.visual.inspection = ImageInspection(file_sha1=file_sha1(img), passed=passed, notes=args.notes or "",
                                                  inspected_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
            run.note(f"scene {s.id}: inspection {'PASS' if passed else 'FAIL'} ({img.name}) — {args.notes or ''}")
        save_episode(ep_dir, ep)


def run_oneoff(args: argparse.Namespace) -> None:
    cfg = load_config()
    icfg = cfg["images"]
    width, height = format_config(cfg, args.format)["image_size"]
    seed = args.seed if args.seed is not None else 1234
    out = Path(args.out) if Path(args.out).is_absolute() else REPO_ROOT / args.out
    secs = get_backend(icfg).generate(full_prompt(args.prompt, icfg), seed, width, height, out)
    print(f"{out}  {width}x{height} seed {seed}  {secs:.1f}s")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode", nargs="?")
    p.add_argument("--scene", type=int, action="append", dest="scenes")
    p.add_argument("--force", action="store_true", help="regenerate existing images (same seed)")
    p.add_argument("--retry", action="store_true", help="next attempt with a new seed (counts toward max_attempts)")
    p.add_argument("--prompt", help="set/replace the image prompt (episode mode) or the prompt to test")
    p.add_argument("--seed", type=int)
    p.add_argument("--format", default="long", choices=["long", "short"], help="one-off mode only")
    p.add_argument("--out", help="one-off mode: output file")
    p.add_argument("--checklist", action="store_true", help="print the image inspection checklist")
    p.add_argument("--crops", action="store_true", help="write 2× zoomed quarter crops to images/inspect/")
    p.add_argument("--extra-attempt", action="store_true",
                   help="allow one attempt beyond images.max_attempts — ONLY when the user explicitly asked for it")
    p.add_argument("--use-attempt", type=int, help="make attempt N (images/scene-XX-aN.png) the current image")
    p.add_argument("--inspect", choices=["pass", "fail"], help="record the inspection result for --scene")
    p.add_argument("--notes", help="what was checked/counted (required for pass)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    setup_logging(args.verbose)
    if args.checklist:
        print(checklist_text(load_config()["images"]))
        return
    if args.episode and (args.crops or args.inspect or args.use_attempt):
        if not args.scenes:
            p.error("--crops/--inspect/--use-attempt need --scene N")
        run_inspection_tools(args)
    elif args.episode:
        if args.retry and not args.scenes:
            p.error("--retry needs --scene N")
        run_episode(args)
    elif args.prompt and args.out:
        run_oneoff(args)
    else:
        p.error("give an episode folder, or --prompt and --out for a one-off image")


if __name__ == "__main__":
    main()
