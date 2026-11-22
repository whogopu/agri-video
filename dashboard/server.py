"""Pipeline control room: a local web dashboard over the episode pipeline.

    uv run python -m dashboard            # → http://127.0.0.1:8765

Shows every episode's status, each stage's last run and its output, and runs stages as jobs
(one at a time, because this Mac runs heavy work serially) with live log, progress, ETA, Stop and Retry.

It only ever runs the same `python -m pipeline.<stage>` commands you'd type; it never edits
episode.json itself and never passes --allow-unapproved, so the status gates and the three human
checkpoints stay exactly as the stages enforce them. Listens on localhost only.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dashboard import flow, usage
from pipeline.common import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = REPO_ROOT / "episodes"
CAST_DIR = REPO_ROOT / "assets" / "cast"
STATIC_DIR = Path(__file__).resolve().parent / "static"
RUNS_DIR = Path(__file__).resolve().parent / "runs"   # job history + logs (gitignored)

STATUSES = ["draft", "script_approved", "narrated", "visuals_ready", "draft_rendered",
            "final_rendered", "reviewed", "packaged"]
CHECKPOINTS = {  # status reached → human checkpoint that has to happen first
    "script_approved": "Checkpoint 1 — you have read script.md and approve the script",
    "final_rendered": "Checkpoint 2 — you have watched render/draft.mp4 and approve it",
    "packaged": "Checkpoint 3 — you approve the final video, thumbnail and youtube.md",
}

# Stages the dashboard can run. `log_names` = how the stage titles itself in log.md.
STAGES: list[dict] = [
    {"key": "text_normalize", "label": "Spoken text", "module": "pipeline.text_normalize", "args": [],
     "needs": "draft", "reaches": None, "heavy": False, "log_names": ["text_normalize"],
     "what": "Builds narration_spoken (numbers → words, pronunciation fixes) for TTS."},
    {"key": "narration", "label": "Narration", "module": "pipeline.narration", "args": [],
     "needs": "script_approved", "reaches": "narrated", "heavy": True, "log_names": ["narration"],
     "what": "TTS takes per sentence, Whisper scores them, best take picked, loudness, word timing."},
    {"key": "images", "label": "Images", "module": "pipeline.images", "args": [],
     "needs": "narrated", "reaches": "visuals_ready", "heavy": True, "log_names": ["images"],
     "what": "FLUX.2 klein stills per shot (cast references for consistent faces). Each needs inspection."},
    {"key": "render_draft", "label": "Draft render", "module": "pipeline.render", "args": ["--draft"],
     "needs": "visuals_ready", "reaches": "draft_rendered", "heavy": True, "log_names": ["render (draft)"],
     "what": "Remotion 540p render → render/draft.mp4 for checkpoint 2."},
    {"key": "review_draft", "label": "Review draft", "module": "pipeline.review", "args": ["--draft"],
     "needs": "draft_rendered", "reaches": None, "heavy": False, "log_names": [],
     "what": "Contact sheets, loudness, black/freeze checks on the draft."},
    {"key": "render_final", "label": "Final render", "module": "pipeline.render", "args": [],
     "needs": "draft_rendered", "reaches": "final_rendered", "heavy": True, "log_names": ["render (final)"],
     "checkpoint": "Checkpoint 2 — you have watched render/draft.mp4 and approve it for the final render",
     "what": "Remotion 1080p render → render/video.mp4."},
    {"key": "review", "label": "Review", "module": "pipeline.review", "args": [],
     "needs": "final_rendered", "reaches": "reviewed", "heavy": False, "log_names": ["review"],
     "what": "Contact sheets + checks → review/review.md."},
    {"key": "package", "label": "Package", "module": "pipeline.package", "args": [],
     "needs": "reviewed", "reaches": "packaged", "heavy": False, "log_names": ["package"],
     "what": "Thumbnail + youtube.md from episode.json `package`, for checkpoint 3."},
]
STAGE_BY_KEY = {s["key"]: s for s in STAGES}

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def rank(status: str) -> int:
    return STATUSES.index(status) if status in STATUSES else -1


def now() -> float:
    return time.time()


# ---------------------------------------------------------------- log.md parsing

HEAD = re.compile(r"^## (.+?) — (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s*$")


def parse_log(path: Path) -> list[dict]:
    """log.md → [{stage, started, duration, outcome, notes[]}] (oldest first)."""
    if not path.exists():
        return []
    entries, cur = [], None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = HEAD.match(line)
        if m:
            cur = {"stage": m.group(1), "started": m.group(2), "duration": None, "outcome": "", "notes": []}
            entries.append(cur)
            continue
        if line.startswith("**FLAG**"):
            entries.append({"stage": "FLAG", "started": "", "duration": None, "outcome": "flag",
                            "notes": [line.replace("**FLAG**", "").strip()]})
            cur = None
            continue
        if cur is None or not line.startswith("- "):
            continue
        body = line[2:]
        if body.startswith("duration: ") and cur["duration"] is None:
            try:
                cur["duration"] = float(body[len("duration: "):].rstrip("s"))
            except ValueError:
                pass
        elif body.startswith("outcome: ") and not cur["outcome"]:
            cur["outcome"] = body[len("outcome: "):]
        else:
            cur["notes"].append(body)
    return entries


# ---------------------------------------------------------------- ETA model (from every episode's history)

class History:
    """Per-unit rates learned from all episodes' log.md + take metadata. Refreshed every 2 min."""

    DEFAULTS = {"image_sec": 20.0, "take_sec": 9.0, "render_draft_per_video_sec": 0.42,
                "render_final_per_video_sec": 0.40}

    def __init__(self) -> None:
        self.loaded_at = 0.0
        self.rates: dict = {}
        self.stage_median: dict[str, float] = {}

    def refresh(self) -> None:
        if now() - self.loaded_at < 120:
            return
        img, take, rd, rf, by_stage = [], [], [], [], {}
        for log_path in EPISODES_DIR.glob("*/log.md"):
            for e in parse_log(log_path):
                d, ok = e["duration"], e["outcome"] == "ok"
                if d is None or not ok:
                    continue
                by_stage.setdefault(e["stage"], []).append(d)
                for n in e["notes"]:
                    m = re.search(r"shot \d+: attempt \d+, seed .*?, ([\d.]+)s →", n)
                    if m:
                        img.append(float(m.group(1)) + 1.0)
                    m = re.match(r"synthesizing (\d+) take", n)
                    if m and d > 20:
                        take.append(d / int(m.group(1)))
                    m = re.search(r"rendering \w+\.mp4: .*expected ([\d.]+)s", n)
                    if m and d > 5:
                        (rd if e["stage"] == "render (draft)" else rf).append(d / float(m.group(1)))
        med = lambda xs, k: statistics.median(xs) if xs else self.DEFAULTS[k]  # noqa: E731
        self.rates = {"image_sec": med(img, "image_sec"), "take_sec": med(take, "take_sec"),
                      "render_draft_per_video_sec": med(rd, "render_draft_per_video_sec"),
                      "render_final_per_video_sec": med(rf, "render_final_per_video_sec"),
                      "samples": {"images": len(img), "takes": len(take), "draft": len(rd), "final": len(rf)}}
        self.stage_median = {k: statistics.median(v) for k, v in by_stage.items()}
        self.loaded_at = now()


HISTORY = History()


def load_episode_json(ep_id: str) -> dict:
    with open(EPISODES_DIR / ep_id / "episode.json", encoding="utf-8") as f:
        return json.load(f)


def video_seconds(ep: dict) -> float:
    """Rough video length: narration + per-scene lead-in/padding (good enough for an ETA)."""
    return sum((s.get("audio") or {}).get("duration_sec") or 4.0 for s in ep.get("scenes", [])) + 1.3 * len(
        ep.get("scenes", []))


def images_todo(ep: dict, ep_dir: Path, scenes: list[int], shots: list[int], force: bool, retry: bool) -> int:
    n = 0
    for s in ep.get("scenes", []):
        v = s.get("visual") or {}
        if v.get("type") != "image" or (scenes and s["id"] not in scenes):
            continue
        for k, sh in enumerate(v.get("shots", []), start=1):
            if shots and k not in shots:
                continue
            f = sh.get("image_file")
            if force or retry or not f or not (ep_dir / f).exists():
                n += 1
    return n


def estimate(stage_key: str, ep_id: str, opts: dict) -> dict:
    """Up-front estimate for a job: {seconds, units, unit_label, basis}."""
    HISTORY.refresh()
    r = HISTORY.rates
    try:
        ep = load_episode_json(ep_id)
    except Exception:
        return {"seconds": None, "basis": "episode.json unreadable"}
    ep_dir = EPISODES_DIR / ep_id
    scenes = opts.get("scenes") or []
    if stage_key == "images":
        n = images_todo(ep, ep_dir, scenes, opts.get("shots") or [], bool(opts.get("force")), bool(opts.get("retry")))
        return {"seconds": n * r["image_sec"], "units": n, "unit_label": "images",
                "basis": f"{n} image(s) × {r['image_sec']:.0f}s (median of {r['samples']['images']} past images)"}
    if stage_key == "narration":
        sel = [s for s in ep.get("scenes", []) if not scenes or s["id"] in scenes]
        if not opts.get("force") and all(s.get("audio") for s in sel):
            return {"seconds": 30, "basis": "audio exists → only re-pick/align (~30s); use Force to redo TTS"}
        sentences = sum(max(1, len(re.findall(r"[।?!]", s.get("narration_display", "")))) for s in sel)
        takes = sentences * int(opts.get("takes") or 3)
        return {"seconds": takes * r["take_sec"], "units": takes, "unit_label": "takes",
                "basis": f"≈{takes} take(s) × {r['take_sec']:.1f}s (TTS + scoring, from past runs)"}
    if stage_key in ("render_draft", "render_final"):
        vs = video_seconds(ep)
        k = "render_draft_per_video_sec" if stage_key == "render_draft" else "render_final_per_video_sec"
        return {"seconds": 15 + vs * r[k], "basis": f"{vs:.0f}s of video × {r[k]:.2f}s per second + bundling"}
    names = STAGE_BY_KEY[stage_key]["log_names"] or [stage_key.split("_")[0]]
    for n in names:
        if n in HISTORY.stage_median:
            return {"seconds": HISTORY.stage_median[n], "basis": f"median of past '{n}' runs"}
    return {"seconds": 10.0 if stage_key in ("review", "review_draft") else 5.0, "basis": "default"}


# ---------------------------------------------------------------- jobs

class Job:
    def __init__(self, ep_id: str, stage: str, label: str, cmd: list[str], opts: dict, est: dict):
        self.id = datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.episode, self.stage, self.label, self.cmd, self.opts, self.est = ep_id, stage, label, cmd, opts, est
        self.state = "queued"          # queued → running → ok | failed | stopped | cancelled
        self.created, self.started, self.ended = now(), None, None
        self.returncode: int | None = None
        self.proc: subprocess.Popen | None = None
        self.lines: list[str] = []
        self.progress = {"done": 0, "total": est.get("units"), "phase": "", "first_unit_at": None}
        self.stop_requested = False
        self.log_path = RUNS_DIR / "logs" / f"{self.id}.log"

    def public(self, with_tail: int = 0) -> dict:
        d = {k: getattr(self, k) for k in ("id", "episode", "stage", "label", "state", "created", "started",
                                           "ended", "returncode", "opts", "est")}
        d["cmd"] = " ".join(self.cmd_display())
        d["elapsed"] = ((self.ended or now()) - self.started) if self.started else None
        d["progress"] = self.progress_view()
        d["line_count"] = len(self.lines)
        if with_tail:
            d["tail"] = self.lines[-with_tail:]
        return d

    def cmd_display(self) -> list[str]:
        return ["uv", "run", "python"] + [str(c).replace(str(REPO_ROOT) + "/", "") for c in self.cmd[1:]]

    def progress_view(self) -> dict:
        p = dict(self.progress)
        p.pop("first_unit_at", None)
        est = self.est.get("seconds")
        elapsed = (now() - self.started) if self.started and self.state == "running" else None
        frac, remaining = None, None
        if self.state == "running" and elapsed is not None:
            done, total = p.get("done") or 0, p.get("total")
            if total:
                frac = min(done / total, 0.99)
                fu = self.progress.get("first_unit_at")
                if done >= 2 and fu:
                    per = (now() - fu) / (done - 1)
                elif est and total:
                    per = est / total
                else:
                    per = None
                remaining = per * (total - done) if per is not None else None
                if p.get("phase") and "scoring" in p["phase"] and est:
                    remaining = max(est - elapsed, 5)
            elif est:
                frac = min(elapsed / est, 0.97) if est > 0 else None
                remaining = max(est - elapsed, 0)
        if self.state in ("ok",):
            frac, remaining = 1.0, 0
        p["fraction"], p["remaining"] = frac, remaining
        return p

    # parse live output for progress hints
    def on_line(self, line: str) -> None:
        self.lines.append(line)
        if getattr(self, "_logf", None):
            self._logf.write(line + "\n")
            self._logf.flush()
        if len(self.lines) > 20000:
            del self.lines[:5000]
        pr = self.progress
        if self.stage == "images" and re.search(r"scene \d+ shot \d+: attempt \d+", line):
            pr["done"] += 1
            pr["first_unit_at"] = pr["first_unit_at"] or now()
            pr["phase"] = "generating images"
        elif self.stage == "narration":
            m = re.search(r"synthesizing (\d+) take", line)
            if m:
                pr["total"], pr["done"], pr["phase"] = int(m.group(1)), 0, "TTS"
                self._take_watch_start = now()
            elif "scoring" in line and "take" in line:
                pr["phase"] = "scoring takes (Whisper)"
            elif "word timing" in line:
                pr["phase"] = "word timing"
            elif "loudness" in line:
                pr["phase"] = "loudness"
        elif self.stage.startswith("render"):
            m = re.findall(r"(\d+)/(\d+)", line)
            if m:
                a, b = map(int, m[-1])
                if b > 50 and a <= b:
                    if pr["done"] == 0:
                        pr["first_unit_at"] = now()
                    pr["done"], pr["total"] = a, b
                    pr["phase"] = "encoding" if "ncod" in line else "rendering frames"
            elif "undl" in line:
                pr["phase"] = "bundling"

    def poll_files(self) -> None:
        """Narration writes one json per finished take; count them for live TTS progress."""
        if self.stage != "narration" or self.progress.get("phase") != "TTS":
            return
        t0 = getattr(self, "_take_watch_start", None)
        if not t0:
            return
        takes = EPISODES_DIR / self.episode / "audio" / "takes"
        try:
            n = sum(1 for f in takes.glob("*.json") if f.stat().st_mtime >= t0 - 1)
        except OSError:
            return
        if n and not self.progress["first_unit_at"]:
            self.progress["first_unit_at"] = now()
        self.progress["done"] = n


class JobRunner:
    """Runs one job at a time (heavy GPU work must not overlap on a 16 GB Mac)."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        RUNS_DIR.joinpath("logs").mkdir(parents=True, exist_ok=True)
        self._load_history()
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._file_poll, daemon=True).start()

    def _load_history(self) -> None:
        f = RUNS_DIR / "jobs.json"
        if not f.exists():
            return
        try:
            for d in json.loads(f.read_text())[-200:]:
                j = Job(d["episode"], d["stage"], d["label"], d["cmdv"], d.get("opts", {}), d.get("est", {}))
                j.id, j.created, j.started, j.ended = d["id"], d["created"], d["started"], d["ended"]
                j.returncode = d.get("returncode")
                j.state = d["state"] if d["state"] not in ("queued", "running") else "stopped"
                if j.log_path.exists():
                    j.lines = j.log_path.read_text(errors="replace").splitlines()[-3000:]
                self.jobs.append(j)
        except Exception as e:  # history is a convenience; never block startup on it
            print(f"(ignoring unreadable job history: {e})", file=sys.stderr)

    def _save(self) -> None:
        data = [{**{k: getattr(j, k) for k in ("id", "episode", "stage", "label", "state", "created", "started",
                                               "ended", "returncode", "opts", "est")}, "cmdv": j.cmd}
                for j in self.jobs[-200:]]
        tmp = RUNS_DIR / "jobs.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        os.replace(tmp, RUNS_DIR / "jobs.json")

    def add(self, job: Job) -> Job:
        with self.lock:
            self.jobs.append(job)
            self._save()
        self.wake.set()
        return job

    def get(self, job_id: str) -> Job | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def running(self) -> Job | None:
        return next((j for j in self.jobs if j.state == "running"), None)

    def stop(self, job: Job) -> None:
        if job.state == "queued":
            job.state, job.ended = "cancelled", now()
            self._save()
            return
        if job.state != "running" or not job.proc:
            return
        job.stop_requested = True
        job.on_line("■ stop requested — sending SIGTERM to the job's process group")
        try:
            os.killpg(job.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        def escalate() -> None:
            time.sleep(8)
            if job.proc and job.proc.poll() is None:
                job.on_line("■ still running after 8s — SIGKILL")
                try:
                    os.killpg(job.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        threading.Thread(target=escalate, daemon=True).start()

    def _file_poll(self) -> None:
        while True:
            j = self.running()
            if j:
                j.poll_files()
            time.sleep(1.0)

    def _loop(self) -> None:
        while True:
            job = next((j for j in self.jobs if j.state == "queued"), None)
            if not job:
                self.wake.wait(2)
                self.wake.clear()
                continue
            self._run(job)

    def _run(self, job: Job) -> None:
        job.state, job.started = "running", now()
        self._save()
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"}
        logf = job._logf = open(job.log_path, "w", encoding="utf-8")
        try:
            job.proc = subprocess.Popen(job.cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        except OSError as e:
            job.on_line(f"could not start: {e}")
            job.state, job.ended = "failed", now()
            job._logf = None
            logf.close()
            self._save()
            return
        job.on_line("$ " + " ".join(job.cmd_display()))
        buf = b""
        assert job.proc.stdout
        while True:
            chunk = job.proc.stdout.read1(4096)
            if not chunk:
                break
            buf += chunk
            # \r-updated progress bars (Remotion) become separate lines
            parts = re.split(rb"\r\n|\n|\r", buf)
            buf = parts.pop()
            for raw in parts:
                line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw.decode("utf-8", errors="replace")).rstrip()
                if line:
                    job.on_line(line)
        if buf.strip():
            job.on_line(buf.decode("utf-8", errors="replace").rstrip())
        cpu_exact, maxrss = None, None
        try:   # wait4 → exact CPU time of the job and every worker it waited for
            _, status, ru = os.wait4(job.proc.pid, 0)
            job.returncode = job.proc.returncode = os.waitstatus_to_exitcode(status)
            cpu_exact, maxrss = ru.ru_utime + ru.ru_stime, int(ru.ru_maxrss)   # macOS: bytes
        except ChildProcessError:
            job.returncode = job.proc.wait()
        job.ended = now()
        if SAMPLER:
            SAMPLER.finish(job.id, job.ended, cpu_exact, maxrss,
                           (job.episode, job.stage, job.label, job.started))
        job.state = "stopped" if job.stop_requested else ("ok" if job.returncode == 0 else "failed")
        job.on_line(f"■ {job.state} (exit {job.returncode}) after {job.ended - job.started:.1f}s")
        job._logf = None
        logf.close()
        job.proc = None
        self._save()


RUNNER: JobRunner | None = None
SAMPLER: usage.Sampler | None = None
CLAUDE: usage.ClaudeUsage | None = None


def running_job_meta():
    j = RUNNER.running() if RUNNER else None
    if j and j.proc:
        return (j.id, j.proc.pid, j.episode, j.stage, j.label)
    return None


def usage_live() -> dict:
    d = SAMPLER.live() if SAMPLER else {"runs": [], "system": {}}
    if CLAUDE and CLAUDE.ready:
        threading.Thread(target=CLAUDE.refresh, daemon=True).start()   # incremental, throttled to 10 s
        d["claude"] = CLAUDE.live()
    return d


# ---------------------------------------------------------------- building commands (whitelist only)

def build_job(body: dict) -> Job:
    ep_id = str(body.get("episode", ""))
    if not SAFE_ID.match(ep_id) or not (EPISODES_DIR / ep_id / "episode.json").exists():
        raise ValueError("unknown episode")
    kind = body.get("stage")
    py = [sys.executable, "-m"]
    ep_arg = f"episodes/{ep_id}"
    opts: dict = {}

    if kind == "advance":
        to = body.get("to")
        if to not in STATUSES:
            raise ValueError("unknown status")
        cp = CHECKPOINTS.get(to)
        if cp and not body.get("confirmed"):
            raise ValueError("this advance is a human checkpoint; confirm it first")
        opts = {"to": to}
        return Job(ep_id, "advance", f"Advance → {to}", py + ["pipeline.validate", ep_arg, "--set-status", to],
                   opts, {"seconds": 1, "basis": "validate"})

    if kind == "image_inspect_crops":  # light helper: writes zoomed crops for inspection
        s, k = int(body["scene"]), int(body["shot"])
        return Job(ep_id, "images", f"Crops scene {s} shot {k}",
                   py + ["pipeline.images", ep_arg, "--scene", str(s), "--shot", str(k), "--crops"],
                   {"scenes": [s], "shots": [k]}, {"seconds": 3, "basis": "crops"})

    st = STAGE_BY_KEY.get(kind)
    if not st:
        raise ValueError("unknown stage")
    if st.get("checkpoint") and not body.get("confirmed"):
        raise ValueError("this stage needs a checkpoint confirmation")
    cmd = py + [st["module"], ep_arg] + list(st["args"])
    scenes = [int(x) for x in (body.get("scenes") or [])]
    shots = [int(x) for x in (body.get("shots") or [])]
    if scenes and kind in ("text_normalize", "narration", "images"):
        for s in scenes:
            cmd += ["--scene", str(s)]
        opts["scenes"] = scenes
    if shots and kind == "images":
        for k in shots:
            cmd += ["--shot", str(k)]
        opts["shots"] = shots
    if body.get("force"):
        cmd.append("--force")
        opts["force"] = True
    if body.get("retry") and kind == "images":
        cmd.append("--retry")
        opts["retry"] = True
    if body.get("takes") and kind == "narration":
        cmd += ["--takes", str(int(body["takes"]))]
        opts["takes"] = int(body["takes"])
    label = st["label"]
    if scenes:
        label += " · scene " + ",".join(map(str, scenes))
    if shots:
        label += " shot " + ",".join(map(str, shots))
    if opts.get("retry"):
        label += " · retry"
    elif opts.get("force"):
        label += " · force"
    return Job(ep_id, kind, label, cmd, opts, estimate(kind, ep_id, opts))


# ---------------------------------------------------------------- episode views

def ep_summary(ep_dir: Path) -> dict | None:
    try:
        ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    return {"id": ep_dir.name, "title": ep.get("title_hi", ""), "status": ep.get("status"),
            "format": ep.get("format"), "voice": (ep.get("voice") or {}).get("preset", ""),
            "scenes": len(ep.get("scenes", [])), "mtime": (ep_dir / "episode.json").stat().st_mtime,
            "test": "phase5-test" in ep_dir.name}


def stage_state(st: dict, status: str, last: dict | None, ep_dir: Path, ep: dict) -> str:
    if rank(status) < rank(st["needs"]):
        return "blocked"
    if last and last["outcome"].startswith("failed"):
        return "failed"
    if st["reaches"] and rank(status) >= rank(st["reaches"]):
        return "done"
    out = {"render_draft": "render/draft.mp4", "render_final": "render/video.mp4",
           "review_draft": "review/review.md", "package": "youtube.md"}.get(st["key"])
    if out and (ep_dir / out).exists() and last:
        return "done"
    if st["key"] == "text_normalize" and ep.get("scenes") and all(s.get("narration_spoken") for s in ep["scenes"]):
        return "done"
    return "ready"


def episode_detail(ep_id: str) -> dict:
    ep_dir = EPISODES_DIR / ep_id
    ep = load_episode_json(ep_id)
    status = ep.get("status", "draft")
    log = parse_log(ep_dir / "log.md")
    stages = []
    for st in STAGES:
        names = st["log_names"] or []
        last = next((e for e in reversed(log) if e["stage"] in names), None)
        if st["key"] in ("review", "review_draft"):  # review and review --draft share the log name
            last = next((e for e in reversed(log) if e["stage"] == "review"), None)
        runs = [e for e in log if e["stage"] in names]
        stages.append({**{k: st[k] for k in ("key", "label", "needs", "reaches", "heavy", "what")},
                       "checkpoint": st.get("checkpoint"), "state": stage_state(st, status, last, ep_dir, ep),
                       "last": last, "runs": len(runs), "estimate": estimate(st["key"], ep_id, {})})
    scenes = []
    for s in ep.get("scenes", []):
        v = s.get("visual") or {}
        shots = []
        for k, sh in enumerate(v.get("shots", []) if v.get("type") == "image" else [], start=1):
            ins = sh.get("inspection")
            f = sh.get("image_file")
            attempts = sorted(p.name for p in (ep_dir / "images").glob(f"scene-{s['id']:02d}-s{k}-a*.png"))
            shots.append({"k": k, "file": f, "exists": bool(f and (ep_dir / f).exists()),
                          "attempts": sh.get("attempts", 0), "attempt_files": attempts,
                          "characters": sh.get("characters", []), "prompt": sh.get("image_prompt") or "",
                          "at_segment": sh.get("at_segment", 0),
                          "inspection": None if not ins else {"passed": ins.get("passed"),
                                                               "notes": ins.get("notes", ""),
                                                               "at": ins.get("inspected_at", "")}})
        a = s.get("audio") or {}
        scenes.append({"id": s["id"], "purpose": s.get("purpose"), "text": s.get("narration_display", ""),
                       "on_screen": s.get("on_screen_text"), "spoken_ready": bool(s.get("narration_spoken")),
                       "visual": v.get("type"), "template": v.get("template"), "shots": shots,
                       "audio": a.get("file"), "duration": a.get("duration_sec"),
                       "verify": "[VERIFY" in s.get("narration_display", "")})
    files = {}
    for rel in ["script.md", "brief.md", "render/draft.mp4", "render/video.mp4", "review/review.md",
                "render/thumbnail.png", "youtube.md", "audio/takes.md"]:
        p = ep_dir / rel
        if p.exists():
            files[rel] = {"size": p.stat().st_size, "mtime": p.stat().st_mtime}
    sheets = sorted(p.name for p in (ep_dir / "review").glob("sheet-*.png")) if (ep_dir / "review").exists() else []
    n_shots = sum(len(s["shots"]) for s in scenes)
    insp = sum(1 for s in scenes for sh in s["shots"] if sh["inspection"] and sh["inspection"]["passed"])
    nxt = STATUSES[rank(status) + 1] if rank(status) + 1 < len(STATUSES) else None
    return {"id": ep_id, "title": ep.get("title_hi", ""), "status": status, "format": ep.get("format"),
            "voice": (ep.get("voice") or {}).get("preset", ""), "cast": ep.get("cast", []),
            "statuses": STATUSES, "checkpoints": CHECKPOINTS, "next_status": nxt,
            "stages": stages, "scenes": scenes, "files": files, "sheets": sheets,
            "counts": {"shots": n_shots, "inspected_pass": insp,
                       "audio": sum(1 for s in scenes if s["audio"]), "scenes": len(scenes),
                       "verify": sum(1 for s in scenes if s["verify"])},
            "log": log[-60:], "video_sec": video_seconds(ep)}


def external_processes() -> list[dict]:
    """Pipeline processes not started by this dashboard (e.g. run by Claude in a terminal)."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,command="], capture_output=True, text=True,
                             timeout=3).stdout
    except Exception:
        return []
    ours = set()
    for j in RUNNER.jobs if RUNNER else []:
        if j.proc:
            ours.add(j.proc.pid)
    procs = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, cmd = int(parts[0]), int(parts[1]), parts[2], parts[3]
        m = re.search(r"-m (pipeline\.\w+)(.*)", cmd)
        if not m or pid in ours or ppid in ours or "dashboard" in cmd:
            continue
        procs.append({"pid": pid, "etime": etime, "module": m.group(1),
                      "args": m.group(2).strip().replace(str(REPO_ROOT) + "/", "")})
    # keep only the top of each tree (uv run → python)
    pids = {p["pid"] for p in procs}
    return [p for p in procs if not any(q["pid"] != p["pid"] and q["pid"] in pids and p["pid"] in _children(q["pid"], out)
                                        for q in procs)]


def _children(pid: int, ps_out: str) -> set[int]:
    kids: dict[int, list[int]] = {}
    for line in ps_out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 2 and parts[0].isdigit():
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
    seen, stack = set(), [pid]
    while stack:
        for c in kids.get(stack.pop(), []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def stop_external(pid: int) -> str:
    if not any(p["pid"] == pid for p in external_processes()):
        return "not a pipeline process"
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,command="], capture_output=True, text=True).stdout
    for p in [pid, *_children(pid, out)]:
        try:
            os.kill(p, signal.SIGTERM)
        except ProcessLookupError:
            pass
    return "SIGTERM sent"


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "pipeline-dashboard"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        path, q = unquote(u.path), parse_qs(u.query)
        try:
            if path in ("/", "/index.html"):
                return self._file(STATIC_DIR / "index.html")
            if path.startswith("/static/"):
                return self._file(STATIC_DIR / path[len("/static/"):], root=STATIC_DIR)
            if path == "/bakeoff":
                return self._file(STATIC_DIR / "bakeoff.html")
            if path == "/api/bakeoff/items":
                from pipeline import bakeoff
                p = bakeoff.BLIND / "items.json"
                data = json.loads(p.read_text()) if p.exists() else {"tags": bakeoff.TAGS, "items": []}
                data["ratings"] = bakeoff.latest_ratings()
                return self._json(data)
            m = re.match(r"^/bakeoff-img/([0-9a-f]{10})$", path)
            if m:
                from pipeline import bakeoff
                img = bakeoff.blind_image(m.group(1))
                if not img:
                    return self._json({"error": "not found"}, 404)
                return self._file(img, root=REPO_ROOT / "bakeoff")
            if path == "/api/episodes":
                eps = [e for d in sorted(EPISODES_DIR.iterdir()) if d.is_dir() and (e := ep_summary(d))]
                return self._json(sorted(eps, key=lambda e: -e["mtime"]))
            if path.startswith("/api/episode/"):
                ep_id = path.split("/")[3]
                if not SAFE_ID.match(ep_id):
                    return self._json({"error": "bad id"}, 400)
                return self._json(episode_detail(ep_id))
            if path.startswith("/api/flow/"):
                ep_id = path.split("/")[3]
                if not SAFE_ID.match(ep_id) or not (EPISODES_DIR / ep_id / "episode.json").exists():
                    return self._json({"error": "bad id"}, 400)
                running = RUNNER.running()
                return self._json(flow.build(ep_id, load_episode_json(ep_id), episode_detail(ep_id), load_config(),
                                             CLAUDE, SAMPLER, parse_log, EPISODES_DIR / ep_id / "log.md",
                                             running.public() if running else None))
            if path == "/api/jobs":
                running = RUNNER.running()
                return self._json({"jobs": [j.public() for j in reversed(RUNNER.jobs[-60:])],
                                   "running": running.public(with_tail=12) if running else None,
                                   "queued": sum(1 for j in RUNNER.jobs if j.state == "queued"),
                                   "external": external_processes(),
                                   "rates": HISTORY.rates,
                                   "usage_live": usage_live()})
            if path == "/api/usage":
                ep = (q.get("episode") or [""])[0] or None
                if ep and not SAFE_ID.match(ep):
                    return self._json({"error": "bad id"}, 400)
                if not CLAUDE.ready:
                    return self._json({"ready": False})
                CLAUDE.refresh()
                return self._json(usage.aggregate(CLAUDE, SAMPLER, parse_log, ep))
            m = re.match(r"^/api/jobs/([\w-]+)/log$", path)
            if m:
                j = RUNNER.get(m.group(1))
                if not j:
                    return self._json({"error": "no such job"}, 404)
                start = int((q.get("from") or ["0"])[0])
                return self._json({"job": j.public(), "from": start, "lines": j.lines[start:start + 5000],
                                   "next": min(len(j.lines), start + 5000)})
            if path.startswith("/files/"):
                rel = path[len("/files/"):]
                if rel.startswith("cast/"):
                    return self._file(CAST_DIR / rel[len("cast/"):], root=CAST_DIR)
                return self._file(EPISODES_DIR / rel, root=EPISODES_DIR)
            return self._json({"error": "not found"}, 404)
        except FileNotFoundError:
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/jobs":
                job = RUNNER.add(build_job(body))
                return self._json(job.public())
            m = re.match(r"^/api/jobs/([\w-]+)/(stop|retry)$", path)
            if m:
                j = RUNNER.get(m.group(1))
                if not j:
                    return self._json({"error": "no such job"}, 404)
                if m.group(2) == "stop":
                    RUNNER.stop(j)
                    return self._json(j.public())
                nj = Job(j.episode, j.stage, j.label, j.cmd, j.opts, estimate(j.stage, j.episode, j.opts)
                         if j.stage in STAGE_BY_KEY else j.est)
                return self._json(RUNNER.add(nj).public())
            if path == "/api/bakeoff/rate":
                from pipeline import bakeoff
                return self._json(bakeoff.record_rating(str(body.get("id", "")), str(body.get("verdict", "")),
                                                        list(body.get("tags") or []), str(body.get("note") or "")))
            if path == "/api/bakeoff/rebuild":
                from pipeline import bakeoff
                return self._json({"items": bakeoff.blind()})
            if path == "/api/validate":
                ep_id, as_ = body.get("episode", ""), body.get("as")
                if not SAFE_ID.match(ep_id) or (as_ and as_ not in STATUSES):
                    return self._json({"error": "bad request"}, 400)
                cmd = [sys.executable, "-m", "pipeline.validate", f"episodes/{ep_id}"] + (["--as", as_] if as_ else [])
                r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
                return self._json({"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()})
            m = re.match(r"^/api/external/(\d+)/stop$", path)
            if m:
                return self._json({"result": stop_external(int(m.group(1)))})
            return self._json({"error": "not found"}, 404)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _file(self, p: Path, root: Path | None = None):
        p = p.resolve()
        if root and not str(p).startswith(str(root.resolve()) + os.sep):
            return self._json({"error": "forbidden"}, 403)
        if not p.is_file():
            raise FileNotFoundError(p)
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix in (".md", ".txt", ".log"):
            ctype = "text/plain; charset=utf-8"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):   # Safari needs ranges for <video>
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main() -> None:
    global RUNNER, SAMPLER, CLAUDE
    p = argparse.ArgumentParser(description="Pipeline control room (local web dashboard)")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    RUNNER = JobRunner()
    SAMPLER = usage.Sampler(RUNS_DIR, running_job_meta)
    SAMPLER.start()
    CLAUDE = usage.ClaudeUsage()
    threading.Thread(target=CLAUDE.refresh, args=(0,), daemon=True).start()   # first full read takes a few s
    HISTORY.refresh()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True
    print(f"Pipeline control room → http://127.0.0.1:{args.port}   (Ctrl-C to quit; running jobs are stopped)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        j = RUNNER.running()
        if j:
            RUNNER.stop(j)


if __name__ == "__main__":
    main()
