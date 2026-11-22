"""Image model bake-off: same scene-spec prompts and seeds through every candidate model, then a
blind comparison (Claude inspects every image; the user rates a shuffled, model-hidden set in the
dashboard at /bakeoff).

    uv run python -m pipeline.bakeoff prompts                       # lint + render specs → bakeoff/prompts/
    uv run python -m pipeline.bakeoff run --model zimage_q8 [--shots B01 B02] [--seeds 11 22] [--force]
    uv run python -m pipeline.bakeoff status                        # images done per model, time, peak memory
    uv run python -m pipeline.bakeoff blind                         # (re)build the shuffled rating set
    uv run python -m pipeline.bakeoff inspect --model M --shot B01 --seed 11 --verdict pass|minor|fail --notes "..."
    uv run python -m pipeline.bakeoff report                        # pass rates → bakeoff/report.md

Models and settings: config.yaml `bakeoff.models`. One image per process, run serially (16 GB, fanless).
Peak memory is macOS `/usr/bin/time -l` "peak memory footprint" of the mflux process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline import scene_spec
from pipeline.common import REPO_ROOT, load_config

BAKEOFF = REPO_ROOT / "bakeoff"
BLIND = BAKEOFF / "blind"
VERDICTS = ("pass", "minor", "fail")      # minor = acceptable with small flaws (counts as a pass)
TAGS = ("hands", "anatomy", "fused people", "physics", "object/tool", "setting", "crop stage", "lesson",
        "clothes", "readable text", "looks fake", "other")


def cfg() -> dict[str, Any]:
    return load_config()["bakeoff"]


def specs() -> dict[str, Any]:
    return scene_spec.load(REPO_ROOT / cfg()["specs"])


def prompts() -> dict[str, str]:
    data = specs()
    out: dict[str, str] = {}
    errors: list[str] = []
    for shot in data["shots"]:
        errs, _warns, prompt = scene_spec.check(shot, data.get("style", ""))
        errors += errs
        out[shot["id"]] = prompt
    if errors:
        raise SystemExit("spec errors:\n  " + "\n  ".join(errors))
    return out


def out_dir(model: str) -> Path:
    return REPO_ROOT / cfg()["out_dir"] / model


def image_path(model: str, shot: str, seed: int) -> Path:
    return out_dir(model) / f"{shot}-s{seed}.png"


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def build_cmd(m: dict[str, Any], prompt: str, seed: int, w: int, h: int, out: Path) -> list[str]:
    cmd = [m["command"], "--model", m["model"], "--prompt", prompt, "--seed", str(seed),
           "--width", str(w), "--height", str(h), "--output", str(out)]
    for key, flag in (("base_model", "--base-model"), ("steps", "--steps"), ("guidance", "--guidance"),
                      ("quantize", "--quantize")):
        if m.get(key) is not None:
            cmd += [flag, str(m[key])]
    return cmd + list(m.get("extra") or [])


REPOS = {    # mflux alias → HF repo (from mflux 0.24 model_config.py)
    "flux2-klein-base-4b": "black-forest-labs/FLUX.2-klein-base-4B", "z-image-turbo": "Tongyi-MAI/Z-Image-Turbo",
    "z-image": "Tongyi-MAI/Z-Image", "flux3-image-klein": "black-forest-labs/flux-3-image-klein",
    "flux3-image-klein-base": "black-forest-labs/flux-3-image-klein-base", "ernie-image": "baidu/ERNIE-Image",
    "krea-2": "krea/Krea-2-Turbo", "qwen-image-2512": "Qwen/Qwen-Image-2512",
}
# Diffusers folders mflux loads; skips duplicate single-file checkpoints, variants/ and ERNIE's pe/ enhancer.
DOWNLOAD_PATTERNS = ["*.json", "*.txt", "*.model", "tokenizer*/**", "scheduler/**", "text_encoder*/**",
                     "transformer/**", "vae/**", "turbo.safetensors"]   # Krea 2 loads its single-file checkpoint
MFLUX_PY = Path.home() / ".local/share/uv/tools/mflux/bin/python"


def download(models: list[str]) -> None:
    """Fetch weights into the HF cache (network only; safe while another heavy job runs)."""
    c = cfg()["models"]
    for name in models:
        repo = REPOS.get(c[name].get("base_model") or c[name]["model"])
        if not repo:
            print(f"{name}: nothing to download (local or pre-quantized repo)")
            continue
        print(f"== downloading {repo}", flush=True)
        code = ("import sys; from huggingface_hub import snapshot_download; "
                "print(snapshot_download(sys.argv[1], allow_patterns=sys.argv[2:]))")
        subprocess.run([str(MFLUX_PY), "-c", code, repo, *DOWNLOAD_PATTERNS], check=True)


def prepare(name: str, m: dict[str, Any], priority: bool = False) -> None:
    """Build the pre-quantized local copy (`save_quantize`) on first use. Quantizing on load kept the
    16-bit text encoder resident: Z-Image q6 used 12 GB and swapped (44 s/step); the saved q6 copy
    (text encoder quantized too) used 6.8 GB at 21 s/step (2026-11-21)."""
    q = m.get("save_quantize")
    path = Path(str(m["model"])).expanduser()
    if not q or path.exists():
        return
    wait_for_quiet(priority=priority)
    print(f"== {name}: saving {m['base_model']} q{q} to {path}", flush=True)
    _run_heavy(["mflux-save", "--model", m["base_model"], "--quantize", str(q), "--path", str(path)], None, check=True)


# Other heavy jobs on this 16 GB Mac: wait for them instead of running alongside (rule: one at a time).
HEAVY = re.compile(r"vlm_worker\.py|mflux-generate|mflux-train|mflux-save|snac_lm_worker|mlx_audio|mlx_whisper|"
                   r"pipeline\.(narration|render|images)\b|remotion.*render")


def other_heavy_jobs() -> list[str]:
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    mine = str(__import__("os").getpid())
    return [l.strip()[:120] for l in out.splitlines()
            if HEAVY.search(l) and "pipeline.bakeoff" not in l and not l.strip().startswith(mine + " ")]


WAITING = BAKEOFF / "logs" / "waiting"   # one marker per priority run waiting for the GPU


def _priority_waiters() -> list[Path]:
    """Live markers of other priority runs (stale ones from dead processes are removed)."""
    import os
    live = []
    for f in WAITING.glob("*.pid") if WAITING.exists() else []:
        pid = int(f.stem)
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, 0)
            live.append(f)
        except OSError:
            f.unlink(missing_ok=True)
    return live


def wait_for_quiet(poll: float = 30.0, priority: bool = False) -> None:
    """Wait until no other heavy job runs. A long round (priority=False) also lets queued priority runs
    (smoke tests) go first between its images; without this a round starved them (2026-11-21)."""
    import os
    said = False
    if not priority:
        while _priority_waiters():
            if not said:
                print("   pausing between images: a priority run is queued", flush=True)
                said = True
            time.sleep(10)
    marker = WAITING / f"{os.getpid()}.pid"
    if priority:
        WAITING.mkdir(parents=True, exist_ok=True)
        marker.touch()
    try:
        while jobs := other_heavy_jobs():
            if not said:
                print(f"   waiting: another heavy job is running ({jobs[0]})", flush=True)
                said = True
            time.sleep(poll if not priority else 5)
    except BaseException:
        marker.unlink(missing_ok=True)
        raise
    # a priority marker stays until the caller's mflux process is running (run() removes it)


def _run_heavy(cmd: list[str], log, check: bool = False) -> subprocess.CompletedProcess:
    """Start the heavy process, then drop this run's priority marker (it now holds the GPU)."""
    import os
    proc = subprocess.Popen(cmd, stdout=log or None, stderr=subprocess.STDOUT if log else None, text=True)
    time.sleep(3)
    (WAITING / f"{os.getpid()}.pid").unlink(missing_ok=True)
    rc = proc.wait()
    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)
    return subprocess.CompletedProcess(cmd, rc)


PEAK = re.compile(r"(\d+)\s+peak memory footprint")
REAL = re.compile(r"([\d.]+)\s+real")


def run(models: list[str], shots: list[str] | None, seeds: list[int] | None, force: bool,
        priority: bool | None = None) -> None:
    """priority (default: a run of at most 2 images per model) jumps ahead of long rounds between images."""
    import os
    c = cfg()
    w, h = c["size"]
    ps = prompts()
    # keep the Mac awake for the whole run (2026-11-21: idle sleep stretched one image from ~13 to ~50 min)
    subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shot_ids = shots or list(ps)
    seeds = seeds or list(c["seeds"])
    for name in models:
        m = c["models"].get(name)
        if m is None:
            raise SystemExit(f"unknown model {name!r}; known: {', '.join(c['models'])}")
        todo = [(s, sd) for s in shot_ids for sd in seeds if force or not image_path(name, s, sd).exists()]
        print(f"== {name}: {len(todo)} image(s) to make", flush=True)
        prio = priority if priority is not None else len(todo) <= 2
        if todo:
            prepare(name, m, prio)
        for i, (shot, seed) in enumerate(todo, 1):
            out = image_path(name, shot, seed)
            out.parent.mkdir(parents=True, exist_ok=True)
            wait_for_quiet(priority=prio)
            print(f"[{i}/{len(todo)}] {name} {shot} seed {seed} ...", flush=True)
            t0 = time.monotonic()
            log = out.with_suffix(".log")      # live mflux output (progress bar: tail -c 300 <log>)
            with log.open("w") as lf:
                proc = _run_heavy(["/usr/bin/time", "-l", *build_cmd(m, ps[shot], seed, w, h, out)], lf)
            secs = time.monotonic() - t0
            text = log.read_text(errors="replace")
            res = subprocess.CompletedProcess(proc.args, proc.returncode, "", text)
            peak = PEAK.search(res.stderr)
            rec = {"model": name, "shot": shot, "seed": seed, "secs": round(secs, 1),
                   "peak_gb": round(int(peak.group(1)) / 1e9, 2) if peak else None,
                   "ok": res.returncode == 0 and out.exists(), "at": datetime.now().isoformat(timespec="seconds"),
                   "settings": {k: m.get(k) for k in ("model", "quantize", "steps", "guidance")}}
            if not rec["ok"]:
                rec["error"] = (res.stderr or res.stdout)[-1500:]
            _append(out_dir(name) / "results.jsonl", rec)
            print(f"   {'ok' if rec['ok'] else 'FAILED'} {secs:.0f}s peak {rec['peak_gb']} GB", flush=True)
            if not rec["ok"]:
                print(rec["error"][-600:], file=sys.stderr, flush=True)
                if i == 1:
                    break       # first image failed (download/memory): don't burn through the rest
            time.sleep(float(c.get("cooldown_sec") or 0))


def status() -> list[dict]:
    rows = []
    for name in cfg()["models"]:
        res = [r for r in _jsonl(out_dir(name) / "results.jsonl") if r.get("ok")]
        first = res[0]["secs"] if res else None   # first run includes download + quantize
        rest = [r["secs"] for r in res[1:]] or ([first] if first else [])
        imgs = sorted(out_dir(name).glob("*.png")) if out_dir(name).exists() else []
        rows.append({"model": name, "images": len(imgs),
                     "median_secs": sorted(rest)[len(rest) // 2] if rest else None,
                     "peak_gb": max((r["peak_gb"] or 0) for r in res) if res else None})
    return rows


# ---- blind set -----------------------------------------------------------------------------------

def _key() -> dict[str, Any]:
    p = BLIND / "key.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"salt": secrets.token_hex(8), "items": {}}


def blind(models: list[str] | None = None) -> int:
    """Give every bake-off image of `models` (default: models with all shots done) an opaque id, keep ids
    stable across rebuilds, shuffle. Single test images stay out so the comparison is between full sets."""
    key = _key()
    data = specs()
    meta = {s["id"]: s for s in data["shots"]}
    ps = prompts()
    if models is None:
        models = [n for n in cfg()["models"] if out_dir(n).exists()
                  and {p.stem.split("-s")[0] for p in out_dir(n).glob("B*-s*.png")} >= set(ps)]
    key["models"] = models
    for name in models:
        for img in sorted(out_dir(name).glob("B*-s*.png")) if out_dir(name).exists() else []:
            shot, seed = img.stem.split("-s")
            bid = hashlib.sha1(f"{key['salt']}|{name}|{shot}|{seed}".encode()).hexdigest()[:10]
            key["items"][bid] = {"model": name, "shot": shot, "seed": int(seed),
                                 "path": str(img.relative_to(REPO_ROOT))}
    BLIND.mkdir(parents=True, exist_ok=True)
    (BLIND / "key.json").write_text(json.dumps(key, indent=1))
    ids = sorted(key["items"])
    random.Random(key["salt"]).shuffle(ids)
    items = [{"id": i, "shot": key["items"][i]["shot"], "title": meta[key["items"][i]["shot"]]["title"],
              "teaches": meta[key["items"][i]["shot"]]["teaches"],
              "notes": meta[key["items"][i]["shot"]].get("inspector_notes", []),
              "prompt": ps[key["items"][i]["shot"]]} for i in ids
             if key["items"][i]["shot"] in meta and key["items"][i]["model"] in models]
    (BLIND / "items.json").write_text(json.dumps({"tags": TAGS, "items": items}, ensure_ascii=False, indent=1))
    return len(items)


def blind_image(bid: str) -> Path | None:
    item = _key()["items"].get(bid)
    return REPO_ROOT / item["path"] if item else None


def record_rating(bid: str, verdict: str, tags: list[str], note: str) -> dict:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    if bid not in _key()["items"]:
        raise ValueError(f"unknown item {bid}")
    rec = {"id": bid, "verdict": verdict, "tags": [t for t in tags if t in TAGS], "note": note[:500],
           "at": datetime.now().isoformat(timespec="seconds")}
    _append(BLIND / "ratings.jsonl", rec)
    return rec


def latest_ratings() -> dict[str, dict]:
    return {r["id"]: r for r in _jsonl(BLIND / "ratings.jsonl")}


def record_inspection(model: str, shot: str, seed: int, verdict: str, notes: str) -> None:
    if verdict not in VERDICTS:
        raise SystemExit(f"verdict must be one of {VERDICTS}")
    if not image_path(model, shot, seed).exists():
        raise SystemExit(f"no image {image_path(model, shot, seed)}")
    if "action:" not in notes:
        raise SystemExit("notes need an 'action:' part (what moves / is held, and whether the physics is right)")
    _append(out_dir(model) / "inspect.jsonl", {"shot": shot, "seed": seed, "verdict": verdict, "notes": notes,
                                               "at": datetime.now().isoformat(timespec="seconds")})


def report() -> str:
    key = _key()["items"]
    user = latest_ratings()
    user_by = {(v["model"], v["shot"], v["seed"]): user[k]["verdict"] for k, v in key.items() if k in user}
    lines = ["# Image model bake-off", "", f"Updated {datetime.now():%Y-%m-%d %H:%M}. Pass = pass or minor.", "",
             "| model | images | Claude pass | user pass | median s/img | peak GB |", "|---|---|---|---|---|---|"]
    st = {r["model"]: r for r in status()}
    for name in cfg()["models"]:
        ins = {(r["shot"], r["seed"]): r["verdict"] for r in _jsonl(out_dir(name) / "inspect.jsonl")}
        u = [v for (m, s, sd), v in user_by.items() if m == name]

        def rate(vs):
            return f"{sum(v != 'fail' for v in vs)}/{len(vs)}" if vs else "-"
        r = st[name]
        lines.append(f"| {name} | {r['images']} | {rate(list(ins.values()))} | {rate(u)} | "
                     f"{r['median_secs'] or '-'} | {r['peak_gb'] or '-'} |")
    text = "\n".join(lines) + "\n"
    (BAKEOFF / "report.md").write_text(text)
    return text


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompts")
    r = sub.add_parser("run")
    r.add_argument("--model", nargs="+", required=True)
    r.add_argument("--shots", nargs="+")
    r.add_argument("--seeds", nargs="+", type=int)
    r.add_argument("--force", action="store_true")
    r.add_argument("--priority", action="store_true", default=None, help="jump ahead of long rounds (default for <=2 images)")
    dl = sub.add_parser("download")
    dl.add_argument("--model", nargs="+")
    sub.add_parser("status")
    bl = sub.add_parser("blind")
    bl.add_argument("--models", nargs="+")
    i = sub.add_parser("inspect")
    i.add_argument("--model", required=True)
    i.add_argument("--shot", required=True)
    i.add_argument("--seed", type=int, required=True)
    i.add_argument("--verdict", required=True, choices=VERDICTS)
    i.add_argument("--notes", required=True)
    sub.add_parser("report")
    a = ap.parse_args(argv)
    if a.cmd == "prompts":
        d = BAKEOFF / "prompts"
        d.mkdir(parents=True, exist_ok=True)
        for sid, p in prompts().items():
            (d / f"{sid}.txt").write_text(p + "\n", encoding="utf-8")
            print(f"{sid}  {len(p.split())} words")
    elif a.cmd == "download":
        download(a.model or list(cfg()["models"]))
    elif a.cmd == "run":
        run(a.model, a.shots, a.seeds, a.force, a.priority)
    elif a.cmd == "status":
        for r in status():
            print(f"{r['model']:22s} {r['images']:3d} images  median {r['median_secs']}s  peak {r['peak_gb']} GB")
    elif a.cmd == "blind":
        print(f"{blind(a.models)} items in bakeoff/blind/items.json")
    elif a.cmd == "inspect":
        record_inspection(a.model, a.shot, a.seed, a.verdict, a.notes)
    elif a.cmd == "report":
        print(report())


if __name__ == "__main__":
    main()
