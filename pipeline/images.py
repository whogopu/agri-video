"""Image stage: generate the stills (shots) of every scene whose visual.type is "image".

    uv run python -m pipeline.images episodes/<id> [--scene N [--shot K]] [--force]
    uv run python -m pipeline.images episodes/<id> --scene N --shot K --retry [--prompt "..."]   # next attempt, new seed
    uv run python -m pipeline.images --prompt "..." --format short --out x.png [--seed 7] [--cast ramesh]  # one-off test
    uv run python -m pipeline.images episodes/<id> --scene N [--shot K] --crops     # zoomed quarters (+ reference side-by-side)
    uv run python -m pipeline.images episodes/<id> --scene N --shot K --inspect pass --notes "..."
    uv run python -m pipeline.images episodes/<id> --scene N --shot K --use-attempt 1   # go back to an earlier attempt
    uv run python -m pipeline.images --checklist                                   # print the inspection checklist
    uv run python -m pipeline.images episodes/<id> --scene N --shot K --checklist   # + this shot's must-show items

Prompts may use {kind:key} tokens from assets/visual_rules.yaml (tested phrases); every prompt is linted
before generating (pipeline/visual_rules.py): naming what you don't want ("no palm trees") is rejected,
because FLUX klein models have no negative prompt and tend to draw what is named.

A scene holds one or more shots (visual.shots); each starts at a narration segment (sentence), so
the picture changes with the narration. A shot that lists `characters` (cast ids, assets/cast/) is
generated in edit mode with those characters' approved reference images, so faces and clothes stay
the same across the whole episode and across episodes.

Every shot must be inspected against config.yaml images.inspection_checklist (anatomy, posture,
dress, tools, text, and identity vs the reference) and the result recorded with --inspect. The
record stores the image's SHA-1, so regenerating clears it; validate blocks visuals_ready until
every shot has a passing inspection of its current file.

Files: every attempt is kept as images/scene-XX-sK-aN.png; the current pick is images/scene-XX-sK.png
(shot.image_file). v1 episodes keep their old images/scene-XX.png names for shot 1.

Backend contract: generate(prompt, seed, width, height, out_path, references=()) -> seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

from pipeline.cast import (load_character, reference_head_path, reference_path, reference_preamble,
                           reference_problems)
from pipeline.common import (
    REPO_ROOT, append_log, format_config, load_config, load_episode, resolve_episode_dir,
    save_episode, selected_scenes, setup_logging, stage_timer,
)
from pipeline.schema import Episode, ImageInspection, Scene, Shot
from pipeline.visual_rules import expand, lint, must_show, prompt_hints, shot_sentence


class MfluxBackend:
    """mflux CLI (MLX) installed as a uv tool. One process per image (FLUX.3 Klein q8: ~120 s, peak 7.8 GB).
    With references it runs images.edit_command (FLUX.3 Klein edit: ~190 s with one reference,
    ~260 s with two, peak 9.0 GB)."""

    def __init__(self, icfg: dict[str, Any]):
        self.cfg = icfg

    def generate(self, prompt: str, seed: int, width: int, height: int, out_path: Path,
                 references: Sequence[Path] = ()) -> float:
        c = self.cfg
        command = c.get("edit_command") if references else c.get("command", "mflux-generate")
        if not command:
            raise RuntimeError("images.edit_command is not set; shots with characters need an edit model")
        cmd = [command, "--model", c["model"],
               "--prompt", prompt, "--seed", str(seed), "--width", str(width), "--height", str(height),
               "--output", str(out_path)]
        if c.get("steps"):
            cmd += ["--steps", str(c["steps"])]
        if references:
            cmd += ["--image-paths", *[str(r) for r in references]]
        if c.get("base_model"):
            cmd += ["--base-model", c["base_model"]]
        if c.get("guidance") is not None:
            cmd += ["--guidance", str(c["guidance"])]
        if c.get("quantize"):
            cmd += ["--quantize", str(c["quantize"])]
        cmd += [str(x) for x in c.get("extra") or []]
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


def full_prompt(prompt: str, icfg: dict[str, Any], preamble: str = "") -> str:
    """Cast preamble + prompt with its {kind:key} tokens expanded (assets/visual_rules.yaml) + style suffix."""
    prompt = expand(prompt)
    suffix = icfg.get("style_suffix", "").strip()
    body = f"{prompt.rstrip(' .,')}, {suffix}" if suffix else prompt
    return f"{preamble} {body}" if preamble else body


def check_prompt(prompt: str, icfg: dict[str, Any], preamble: str = "", where: str = "") -> None:
    """Lint the whole prompt (preamble, shot prompt, suffix) before spending a generation on it.
    Errors (negations, unknown tokens) stop the stage; warnings are printed."""
    errors, warnings = lint(f"{preamble} {prompt}, {icfg.get('style_suffix', '')}")
    tag = f"{where}: " if where else ""
    for w in warnings:
        print(f"  prompt warning {tag}{w}", file=sys.stderr)
    if errors:
        raise SystemExit(f"{tag}image prompt rejected:\n  " + "\n  ".join(errors))


def shot_must_show(scene: Scene, shot: Shot) -> list[str]:
    """This shot's must-show items (visual_rules.yaml) from its prompt tokens and its narration sentence."""
    sentence = shot_sentence(scene.model_dump(), shot.model_dump(), [x.model_dump() for x in scene.visual.shots])
    return must_show(shot.image_prompt or "", sentence)


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


def write_identity_pair(image: Path, ref: Path, out: Path) -> Path:
    """Reference (left) and shot (right) at the same height, for the identity check."""
    a, b = Image.open(ref).convert("RGB"), Image.open(image).convert("RGB")
    h = max(a.height, b.height)
    a = a.resize((round(a.width * h / a.height), h), Image.LANCZOS)
    b = b.resize((round(b.width * h / b.height), h), Image.LANCZOS)
    pair = Image.new("RGB", (a.width + b.width + 16, h), "white")
    pair.paste(a, (0, 0))
    pair.paste(b, (a.width + 16, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    pair.save(out)
    return out


def pass_notes_problem(notes: str | None, has_cast: bool) -> str | None:
    """Why `--inspect pass` notes are not enough, or None. Every pass must record what was counted, an
    `action:` check (where poured/thrown material comes from, container angle, how it lands, the action
    matching the narration and good practice; 'action: static' for a still scene) and, for cast shots,
    `identity:`. User rule 2026-11-20 after a passed shot showed khaad pouring out of a closed fist."""
    text = (notes or "").strip().lower()
    if not text:
        return ("--inspect pass needs --notes with what you counted (arms, hands, fingers, legs per person; "
                "tools; action; for cast: face/hair/clothes match the reference)")
    if "action:" not in text:
        return ("--inspect pass needs an 'action:' check in --notes: trace any poured/thrown/sprayed material to "
                "its source (open hand, tilted container mouth, nozzle — never a closed fist or upright bucket), "
                "how it lands, and that the action matches the narration and good practice "
                "(e.g. 'action: granules leave open right palm, bucket upright in left hand, spread thinly'); "
                "for a still scene write 'action: static'")
    if has_cast and "identity" not in text:
        return ("shots with cast members need an identity check in --notes "
                "(e.g. 'identity: ramesh face/hair/moustache/kurta+gamchha match ref')")
    return None


def default_seed(episode_id: str, scene_id: int, attempt: int, shot: int = 1) -> int:
    """Deterministic per episode/scene/shot/attempt, so reruns reproduce and retries differ.
    Shot 1 keeps the v1 formula, so v1 seeds stay valid."""
    key = f"{episode_id}:{scene_id}:{attempt}" if shot == 1 else f"{episode_id}:{scene_id}.{shot}:{attempt}"
    return int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) % 1_000_000


def shot_stem(scene_id: int, k: int) -> str:
    return f"scene-{scene_id:02d}-s{k}"


def selected_shots(scene: Scene, shot_ids: list[int] | None) -> list[tuple[int, Shot]]:
    shots = list(enumerate(scene.visual.shots, 1))
    if not shot_ids:
        return shots
    bad = [k for k in shot_ids if not 1 <= k <= len(shots)]
    if bad:
        raise SystemExit(f"scene {scene.id} has {len(shots)} shot(s); no shot {bad}")
    return [(k, sh) for k, sh in shots if k in shot_ids]


def cast_references(ep: Episode, shot: Shot) -> tuple[list[Path], str, dict[str, str]]:
    """Reference images, prompt preamble and reference SHA-1s for the characters in a shot."""
    chars = []
    for cid in shot.characters:
        if cid not in ep.cast:
            raise SystemExit(f"character {cid!r} is not in episode.cast {ep.cast}")
        c = load_character(cid)
        probs = reference_problems(c)
        if probs:
            raise SystemExit("; ".join(probs))
        chars.append(c)
    return [shot_reference(c) for c in chars], reference_preamble(chars), {c.id: c.reference_sha1 for c in chars}


def shot_reference(c) -> Path:
    """The image passed to the edit model: images.reference_crop = head (head-and-shoulders crop) or full."""
    crop = load_config()["images"].get("reference_crop", "full")
    return reference_head_path(c) if crop == "head" else reference_path(c)


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
        flagged, made = [], []
        for s in scenes:
            if not s.visual.shots:
                raise SystemExit(f"scene {s.id}: image scene without shots (visual.shots)")
            todo = selected_shots(s, args.shots)
            if args.prompt and len(todo) != 1:
                raise SystemExit("--prompt needs exactly one shot (--scene N --shot K)")
            for k, sh in todo:
                if args.prompt:
                    sh.image_prompt = args.prompt
                if not sh.image_prompt:
                    raise SystemExit(f"scene {s.id} shot {k}: no image_prompt")
                refs, preamble, ref_sha = cast_references(ep, sh)
                check_prompt(sh.image_prompt, icfg, preamble, f"scene {s.id} shot {k}")
                stale = bool(sh.characters) and sh.reference_sha1 != ref_sha and sh.image_file is not None
                current = ep_dir / sh.image_file if sh.image_file else None
                if current and current.exists() and not (args.force or args.retry or stale):
                    continue
                if args.retry or sh.attempts == 0 or stale:
                    attempt = sh.attempts + 1
                else:
                    attempt = sh.attempts  # --force: redo the current attempt with the same seed
                if attempt > max_attempts and not args.extra_attempt:
                    msg = (f"scene {s.id} shot {k}: reached {max_attempts} image attempts; needs a human decision "
                           f"(fewer people, a graphic, or a different idea)")
                    append_log(ep_dir, f"\n**FLAG** {msg}")
                    flagged.append(f"{s.id}.{k}")
                    continue
                seed = args.seed if args.seed is not None else (
                    sh.seed if (sh.seed is not None and not (args.retry or stale))
                    else default_seed(ep.id, s.id, attempt, k))
                stem = shot_stem(s.id, k)
                attempt_file = ep_dir / "images" / f"{stem}-a{attempt}.png"
                final = ep_dir / "images" / f"{stem}.png"
                secs = backend.generate(full_prompt(sh.image_prompt, icfg, preamble), seed, width, height,
                                        attempt_file, refs)
                shutil.copyfile(attempt_file, final)
                sh.seed, sh.attempts, sh.reference_sha1 = seed, attempt, ref_sha
                sh.inspection = None  # new pixels → must be inspected again
                sh.image_file = f"images/{final.name}"
                save_episode(ep_dir, ep)  # save after each image so a crash keeps finished work
                made.append((s, k, sh))
                who = f", cast {'+'.join(sh.characters)}" if sh.characters else ""
                run.note(f"scene {s.id} shot {k}: attempt {attempt}, seed {seed}{who}, {secs:.1f}s → {attempt_file.name}")
        if flagged:
            print(f"Flagged for the user (max attempts reached): shots {flagged}", file=sys.stderr)
    print("Inspect EVERY shot at full size, plus zoomed crops (--crops), person by person, against:")
    print(checklist_text(icfg))
    print("Then record each result:  --scene N --shot K --inspect pass|fail --notes \"<per-person counts; identity>\"")
    for s, k, sh in made:
        print(f"  {ep_dir.name}/{sh.image_file}  (scene {s.id} shot {k}: {sh.image_prompt[:60]})")
        for m in shot_must_show(s, sh):
            print(f"      must show: {m}")


def print_shot_rules(args: argparse.Namespace) -> None:
    """Shot-specific must-show items and library hints (assets/visual_rules.yaml) for --checklist."""
    ep = load_episode(resolve_episode_dir(args.episode))
    for s in selected_scenes(ep, args.scenes):
        if s.visual.type != "image":
            continue
        for k, sh in selected_shots(s, args.shots):
            sentence = shot_sentence(s.model_dump(), sh.model_dump(), [x.model_dump() for x in s.visual.shots])
            print(f"\nscene {s.id} shot {k} — narration: {sentence}")
            items = shot_must_show(s, sh)
            for m in items:
                print(f"  [ ] must show: {m}")
            if not items:
                print("  (no shot-specific rules matched)")
            for h in prompt_hints(sentence, sh.image_prompt or ""):
                print(f"  prompt hint: {h}")


def run_inspection_tools(args: argparse.Namespace) -> None:
    ep_dir = resolve_episode_dir(args.episode)
    ep = load_episode(ep_dir)
    scenes = [s for s in selected_scenes(ep, args.scenes) if s.visual.type == "image"]
    targets = [(s, k, sh) for s in scenes for k, sh in selected_shots(s, args.shots) if sh.image_file]
    if not targets:
        raise SystemExit("no generated shots selected")
    if args.use_attempt:
        with stage_timer(ep_dir, "images (use earlier attempt)") as run:
            for s, k, sh in targets:
                cands = [ep_dir / "images" / f"{shot_stem(s.id, k)}-a{args.use_attempt}.png"]
                if k == 1:
                    cands.append(ep_dir / "images" / f"scene-{s.id:02d}-a{args.use_attempt}.png")  # v1 names
                src = next((c for c in cands if c.exists()), None)
                if src is None:
                    raise SystemExit(f"{cands[0].name} not found")
                shutil.copyfile(src, ep_dir / sh.image_file)
                if args.seed is not None:
                    sh.seed = args.seed
                if args.prompt:
                    sh.image_prompt = args.prompt
                sh.inspection = None  # different pixels → inspect again
                run.note(f"scene {s.id} shot {k}: now using {src.name} (seed {sh.seed})")
            save_episode(ep_dir, ep)
        return
    if args.crops:
        for s, k, sh in targets:
            img = ep_dir / sh.image_file
            for c in write_crops(img, ep_dir / "images" / "inspect"):
                print(c.relative_to(REPO_ROOT))
            for cid in sh.characters:
                ref = reference_path(load_character(cid))
                if ref and ref.exists():
                    pair = write_identity_pair(img, ref, ep_dir / "images" / "inspect" / f"{img.stem}-vs-{cid}.png")
                    print(f"{pair.relative_to(REPO_ROOT)}   ← identity check: {cid}")
        return
    if not args.shots and any(len(s.visual.shots) > 1 for s, _, _ in targets):
        raise SystemExit("this scene has several shots: inspect them one at a time with --shot K")
    passed = args.inspect == "pass"
    if passed:
        problem = pass_notes_problem(args.notes, any(sh.characters for _, _, sh in targets))
        if problem:
            raise SystemExit(problem)
    with stage_timer(ep_dir, "image inspection") as run:
        for s, k, sh in targets:
            img = ep_dir / sh.image_file
            sh.inspection = ImageInspection(file_sha1=file_sha1(img), passed=passed, notes=args.notes or "",
                                            inspected_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
            run.note(f"scene {s.id} shot {k}: inspection {'PASS' if passed else 'FAIL'} ({img.name}) — {args.notes or ''}")
        save_episode(ep_dir, ep)


def run_oneoff(args: argparse.Namespace) -> None:
    cfg = load_config()
    icfg = cfg["images"]
    width, height = format_config(cfg, args.format)["image_size"]
    seed = args.seed if args.seed is not None else 1234
    out = Path(args.out) if Path(args.out).is_absolute() else REPO_ROOT / args.out
    refs, preamble = [], ""
    if args.cast:
        chars = [load_character(c) for c in args.cast]
        for c in chars:
            if reference_problems(c):
                raise SystemExit("; ".join(reference_problems(c)))
        refs, preamble = [shot_reference(c) for c in chars], reference_preamble(chars)
    check_prompt(args.prompt, icfg, preamble)
    secs = get_backend(icfg).generate(full_prompt(args.prompt, icfg, preamble), seed, width, height, out, refs)
    print(f"{out}  {width}x{height} seed {seed}  {secs:.1f}s")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode", nargs="?")
    p.add_argument("--scene", type=int, action="append", dest="scenes")
    p.add_argument("--shot", type=int, action="append", dest="shots", help="shot number within the scene (1-based)")
    p.add_argument("--force", action="store_true", help="regenerate existing images (same seed)")
    p.add_argument("--retry", action="store_true", help="next attempt with a new seed (counts toward max_attempts)")
    p.add_argument("--prompt", help="set/replace the shot's image prompt (episode mode) or the prompt to test")
    p.add_argument("--seed", type=int)
    p.add_argument("--format", default="long", choices=["long", "short"], help="one-off mode only")
    p.add_argument("--out", help="one-off mode: output file")
    p.add_argument("--cast", nargs="+", help="one-off mode: cast ids to condition on")
    p.add_argument("--checklist", action="store_true", help="print the image inspection checklist")
    p.add_argument("--crops", action="store_true",
                   help="write 2× zoomed quarter crops (and reference|shot pairs for cast) to images/inspect/")
    p.add_argument("--extra-attempt", action="store_true",
                   help="allow one attempt beyond images.max_attempts — ONLY when the user explicitly asked for it")
    p.add_argument("--use-attempt", type=int, help="make attempt N the current image of the shot")
    p.add_argument("--inspect", choices=["pass", "fail"], help="record the inspection result for --scene/--shot")
    p.add_argument("--notes", help="what was checked/counted (required for pass)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    setup_logging(args.verbose)
    if args.checklist:
        print(checklist_text(load_config()["images"]))
        if args.episode and args.scenes:
            print_shot_rules(args)
        return
    if args.shots and not args.scenes:
        p.error("--shot needs --scene N")
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
