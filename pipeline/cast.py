"""Recurring characters (the channel's cast), so the same farmer looks the same in every shot.

    uv run python -m pipeline.cast list
    uv run python -m pipeline.cast new ramesh --name-hi "रमेश जी" --name-en Ramesh --gender male \
        --role "farmer, main character" --look "..." --wardrobe "..." [--accessories "bare wrists, ..."]
    uv run python -m pipeline.cast candidates ramesh [--n 4] [--force]   # reference candidates (text-to-image)
    uv run python -m pipeline.cast sheet ramesh                          # numbered sheet of candidates for the USER
    uv run python -m pipeline.cast approve ramesh 2                      # ONLY after the user picked candidate 2

Each character lives in assets/cast/<id>/: character.json (schema.CastMember), ref.png (the
approved reference, committed), candidates/ (gitignored). Shots that list a character are made with
FLUX.2 klein in edit mode, conditioned on the reference images, and their prompt starts with
reference_preamble(): name, "the person in reference image N", look and the fixed wardrobe.

Synthetic people only. Never a real person's face, name or likeness (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont



from pipeline.common import REPO_ROOT, format_config, load_config, setup_logging, write_json
from pipeline.schema import CastMember

CAST_DIR = REPO_ROOT / "assets" / "cast"


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def char_dir(cid: str) -> Path:
    return CAST_DIR / cid


def load_character(cid: str) -> CastMember:
    f = char_dir(cid) / "character.json"
    if not f.exists():
        raise SystemExit(f"unknown cast member {cid!r} (no {rel(f)})")
    return CastMember.model_validate(json.loads(f.read_text(encoding="utf-8")))


def save_character(c: CastMember) -> None:
    write_json(char_dir(c.id) / "character.json", c.model_dump(mode="json"))


def all_characters() -> list[CastMember]:
    if not CAST_DIR.exists():
        return []
    return [load_character(d.name) for d in sorted(CAST_DIR.iterdir()) if (d / "character.json").exists()]


def file_sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def reference_path(c: CastMember) -> Path | None:
    return char_dir(c.id) / c.reference if c.reference else None


def reference_problems(c: CastMember) -> list[str]:
    """Why this character can't be used in shots yet (empty list = usable)."""
    ref = reference_path(c)
    if not ref or not c.approved_at:
        return [f"{c.id}: no approved reference (cast candidates {c.id}, then the user picks one)"]
    if not ref.exists():
        return [f"{c.id}: reference file missing: {rel(ref)}"]
    if file_sha1(ref) != c.reference_sha1:
        return [f"{c.id}: reference image changed after approval; approve it again"]
    return []


def reference_preamble(chars: list[CastMember]) -> str:
    """Prompt text tying each name to its reference image, with look + fixed wardrobe.
    Repeating the wardrobe matters: tests showed klein takes clothes from the prompt more than from
    the reference. Accessories are stated positively ("hair uncovered, bare wrists"): klein has no
    negative prompt, and "no wristwatch" / "nothing added" tended to add them (A/B 2026-11-20)."""
    parts = []
    for i, c in enumerate(chars, 1):
        pron = "his" if c.gender == "male" else "her"
        parts.append(
            f"{c.name_en} is the {'man' if c.gender == 'male' else 'woman'} in reference image {i}: "
            f"keep exactly {pron} face, hair, facial features, age and build ({c.look}) and {pron} clothes "
            f"({c.wardrobe}){'; ' + c.accessories if c.accessories else ''}.")
    return " ".join(parts)


def reference_prompt(c: CastMember) -> str:
    """Text-to-image prompt for a reference candidate: full figure, face clear, plain wall, final costume."""
    return (f"Character reference photo of {c.look}, wearing {c.wardrobe}"
            f"{', ' + c.accessories if c.accessories else ''}, "
            f"standing facing the camera with a calm natural expression, full figure visible from head to feet, "
            f"in front of a plain whitewashed mud wall, soft even daylight, sharp focus on the face, "
            f"both hands relaxed at the sides")


def candidate_seed(cid: str, k: int) -> int:
    return int(hashlib.sha1(f"cast:{cid}:{k}".encode()).hexdigest()[:8], 16) % 1_000_000


def cmd_candidates(args: argparse.Namespace) -> None:
    from pipeline.images import full_prompt, get_backend
    cfg = load_config()
    icfg = cfg["images"]
    c = load_character(args.id)
    width, height = format_config(cfg, "long")["image_size"]
    backend = get_backend(icfg)
    out_dir = char_dir(c.id) / "candidates"
    for k in range(1, args.n + 1):
        out = out_dir / f"c{k}.png"
        if out.exists() and not args.force:
            continue
        seed = candidate_seed(c.id, k)
        secs = backend.generate(full_prompt(reference_prompt(c), icfg), seed, width, height, out)
        if seed not in c.candidate_seeds:
            c.candidate_seeds.append(seed)
        print(f"{rel(out)}  seed {seed}  {secs:.1f}s")
    save_character(c)
    print(f"Inspect each candidate (anatomy, dress, face), then show the user: cast sheet {c.id}")


def cmd_sheet(args: argparse.Namespace) -> None:
    """Numbered side-by-side sheet so the user can pick a face (picking only; inspect at full size)."""
    d = char_dir(args.id) / "candidates"
    files = sorted(d.glob("c*.png"), key=lambda p: int(p.stem[1:]))
    if not files:
        raise SystemExit(f"no candidates in {rel(d)}")
    thumbs = [Image.open(f).convert("RGB") for f in files]
    w, h = 672, int(672 * thumbs[0].height / thumbs[0].width)
    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=48)
    for i, (f, im) in enumerate(zip(files, thumbs)):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im.resize((w, h), Image.LANCZOS), (x, y))
        draw.rectangle((x, y, x + 90, y + 70), fill="black")
        draw.text((x + 20, y + 8), f.stem[1:], fill="white", font=font)
    out = char_dir(args.id) / "candidates" / "sheet.png"
    sheet.save(out)
    print(rel(out))


def cmd_approve(args: argparse.Namespace) -> None:
    c = load_character(args.id)
    src = char_dir(c.id) / "candidates" / f"c{args.candidate}.png"
    if not src.exists():
        raise SystemExit(f"{rel(src)} not found")
    dst = char_dir(c.id) / "ref.png"
    shutil.copyfile(src, dst)
    c.reference, c.reference_sha1 = dst.name, file_sha1(dst)
    c.approved_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.notes = (c.notes + f" Reference = candidate {args.candidate} (approved by the user {c.approved_at}).").strip()
    save_character(c)
    print(f"{c.id}: reference approved → {rel(dst)}. Shots made with the old reference must be regenerated.")


def cmd_new(args: argparse.Namespace) -> None:
    f = char_dir(args.id) / "character.json"
    if f.exists() and not args.force:
        raise SystemExit(f"{rel(f)} exists (use --force to overwrite)")
    c = CastMember(id=args.id, name_hi=args.name_hi, name_en=args.name_en, role=args.role, gender=args.gender,
                   look=args.look, wardrobe=args.wardrobe, accessories=args.accessories)
    save_character(c)
    print(rel(f))


def cmd_list(_: argparse.Namespace) -> None:
    chars = all_characters()
    if not chars:
        print("no cast members yet (assets/cast/)")
    for c in chars:
        probs = reference_problems(c)
        state = "approved" if not probs else "NOT USABLE: " + "; ".join(probs)
        print(f"{c.id:12} {c.name_hi} ({c.name_en}), {c.role} — {state}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    n = sub.add_parser("new")
    n.add_argument("id")
    for a in ("--name-hi", "--name-en", "--role", "--look", "--wardrobe"):
        n.add_argument(a, required=True)
    n.add_argument("--gender", choices=["male", "female"], required=True)
    n.add_argument("--accessories", default="",
                   help='positive wording, e.g. "hair uncovered, bare wrists, bare fingers" (never "no ...")')
    n.add_argument("--force", action="store_true")
    c = sub.add_parser("candidates")
    c.add_argument("id")
    c.add_argument("--n", type=int, default=4)
    c.add_argument("--force", action="store_true")
    s = sub.add_parser("sheet")
    s.add_argument("id")
    a = sub.add_parser("approve", help="ONLY after the user picked a candidate")
    a.add_argument("id")
    a.add_argument("candidate", type=int)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    setup_logging(args.verbose)
    {"list": cmd_list, "new": cmd_new, "candidates": cmd_candidates, "sheet": cmd_sheet,
     "approve": cmd_approve}[args.cmd](args)


if __name__ == "__main__":
    main()
