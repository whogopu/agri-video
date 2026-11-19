"""B-roll library tools. The library is assets/broll/clips/ + assets/broll/index.json.

    uv run python -m pipeline.broll index            # probe new clips, extract frames, add stub entries
    uv run python -m pipeline.broll check            # entries missing descriptions/license, missing files
    uv run python -m pipeline.broll list [--tag wheat] [--orientation portrait]

`index` writes one stub entry per new clip and a contact strip of 3 frames (start, middle, end)
at assets/broll/frames/<id>.jpg. Claude then LOOKS at each strip and fills in the descriptions,
tags, quality notes, source and license (index-broll skill). A clip without a known license
is never used (`check` fails and episode validation can't pick it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pipeline.audio import run as run_cmd
from pipeline.common import REPO_ROOT, setup_logging, write_json

LIBRARY = REPO_ROOT / "assets" / "broll"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
TAG_KEYS = ["crop", "activity", "setting", "season", "shot_type"]
REQUIRED_TEXT = ["description_en", "description_hi", "source", "license"]


def clip_id(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


def probe(path: Path) -> dict[str, Any]:
    res = run_cmd(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)])
    d = json.loads(res.stdout)
    st = d["streams"][0]
    num, den = (int(x) for x in st["r_frame_rate"].split("/"))
    return {"duration_sec": round(float(d["format"]["duration"]), 3), "width": st["width"],
            "height": st["height"], "fps": round(num / den, 3) if den else None}


def contact_strip(path: Path, duration: float, out: Path) -> None:
    """3 frames (5%, 50%, 95%) side by side, each 640 px wide (portrait clips: 360)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    times = [duration * f for f in (0.05, 0.5, 0.95)]
    inputs: list[str] = []
    for t in times:
        inputs += ["-ss", f"{t:.2f}", "-i", str(path)]
    graph = ";".join(f"[{i}:v]trim=end_frame=1,scale='if(gt(iw,ih),640,360)':-2,setsar=1[f{i}]" for i in range(3))
    graph += ";[f0][f1][f2]hstack=inputs=3"
    run_cmd(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-frames:v", "1", "-q:v", "3", str(out)])


def load_index(lib: Path) -> dict[str, Any]:
    p = lib / "index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"clips": []}


def save_index(lib: Path, idx: dict[str, Any]) -> None:
    idx["clips"].sort(key=lambda c: c["id"])
    write_json(lib / "index.json", idx)


def stub_entry(cid: str, file: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": cid, "file": file, **meta,
        "orientation": "portrait" if meta["height"] > meta["width"] else "landscape",
        "frames": f"frames/{cid}.jpg",
        "description_en": "", "description_hi": "",
        "tags": {k: [] for k in TAG_KEYS},
        "usable_segments": [],  # [{"in": 2.0, "out": 9.5, "note": "steady pan"}]
        "quality_notes": "",
        "people_visible": None,  # true → identifiable faces; needs consent before use
        "source": "",            # own footage / Pexels / Pixabay / field staff name …
        "license": "",           # e.g. "own", "Pexels License", "Pixabay Content License"
        "source_url": "",
    }


def entry_problems(c: dict[str, Any], lib: Path) -> list[str]:
    probs = [f"{k} empty" for k in REQUIRED_TEXT if not str(c.get(k, "")).strip()]
    if not any(c.get("tags", {}).get(k) for k in TAG_KEYS):
        probs.append("no tags")
    if c.get("people_visible") is None:
        probs.append("people_visible not set")
    if not (lib / "clips" / c["file"]).exists():
        probs.append(f"file missing: clips/{c['file']}")
    return probs


def is_usable(c: dict[str, Any], lib: Path = LIBRARY) -> bool:
    return not entry_problems(c, lib)


def cmd_index(lib: Path) -> int:
    idx = load_index(lib)
    known = {c["file"] for c in idx["clips"]}
    new = sorted(p for p in (lib / "clips").iterdir() if p.suffix.lower() in VIDEO_EXT and p.name not in known)
    ids = {c["id"] for c in idx["clips"]}
    for p in new:
        cid = clip_id(p)
        while cid in ids:
            cid += "-b"
        meta = probe(p)
        contact_strip(p, meta["duration_sec"], lib / "frames" / f"{cid}.jpg")
        idx["clips"].append(stub_entry(cid, p.name, meta))
        ids.add(cid)
        print(f"+ {cid}: {meta['width']}x{meta['height']} {meta['fps']}fps {meta['duration_sec']}s → frames/{cid}.jpg")
    save_index(lib, idx)
    print(f"{len(new)} new clip(s); {len(idx['clips'])} in library."
          + (" Now look at each frames/<id>.jpg and fill in the entry (index-broll skill)." if new else ""))
    return 0


def cmd_check(lib: Path) -> int:
    idx = load_index(lib)
    bad = 0
    for c in idx["clips"]:
        probs = entry_problems(c, lib)
        if probs:
            bad += 1
            print(f"{c['id']}: {'; '.join(probs)}")
    print(f"{len(idx['clips']) - bad}/{len(idx['clips'])} clips complete and usable")
    return 1 if bad else 0


def cmd_list(lib: Path, tag: str | None, orientation: str | None) -> int:
    for c in load_index(lib)["clips"]:
        tags = [t for k in TAG_KEYS for t in c.get("tags", {}).get(k, [])]
        if tag and tag not in tags:
            continue
        if orientation and c.get("orientation") != orientation:
            continue
        flag = "" if is_usable(c, lib) else "  [INCOMPLETE — not usable]"
        print(f"{c['id']}  {c['duration_sec']}s {c['orientation']}  {', '.join(tags)}{flag}\n    {c.get('description_en', '')}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["index", "check", "list"])
    p.add_argument("--library", type=Path, default=LIBRARY, help=argparse.SUPPRESS)  # tests
    p.add_argument("--tag")
    p.add_argument("--orientation", choices=["landscape", "portrait"])
    args = p.parse_args()
    setup_logging()
    lib = args.library
    (lib / "clips").mkdir(parents=True, exist_ok=True)
    if args.command == "index":
        sys.exit(cmd_index(lib))
    if args.command == "check":
        sys.exit(cmd_check(lib))
    sys.exit(cmd_list(lib, args.tag, args.orientation))


if __name__ == "__main__":
    main()
