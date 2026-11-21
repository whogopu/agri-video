"""Where the compute and the money go: local runs (CPU, GPU, power) and Claude (tokens → $).

Local side — `Sampler` watches every pipeline run, both dashboard jobs and `python -m pipeline.*`
started from a terminal (e.g. by Claude). Every 2 s it reads `ps` (CPU time and memory per process,
grouped into components: FLUX image model, TTS worker, Whisper scoring, Remotion browser, ffmpeg, …),
Apple GPU utilisation (`ioreg IOAccelerator`, no sudo) and whole-Mac power draw
(`ioreg AppleSmartBattery` SystemLoad, mW; macOS refreshes it about once a minute). A finished run
is appended to dashboard/runs/usage.jsonl. Dashboard jobs get exact CPU seconds from wait4() rusage.

Claude side — `ClaudeUsage` reads this project's Claude Code transcripts
(~/.claude/projects/<repo-slug>/*.jsonl), takes each assistant message's token usage once, prices it
with config.yaml `costs.claude_usd_per_mtok` and assigns it to an episode and a pipeline step from
the tools that message used (a Read of images/*.png → image inspection, a Write of script.md →
script, an Edit under pipeline/ → pipeline development, …). Messages without a tool inherit the
session's current step. On a subscription this is the API-equivalent value, not the bill.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = REPO_ROOT / "episodes"
TRANSCRIPTS_DIR = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(REPO_ROOT))

# One axis shared by local stages and Claude work, in pipeline order.
STEPS: list[tuple[str, str]] = [
    ("script", "Script & research"),
    ("text_normalize", "Spoken text"),
    ("narration", "Narration (TTS + scoring)"),
    ("cast", "Cast faces"),
    ("images", "Image generation & prompts"),
    ("image_inspection", "Image inspection"),
    ("render", "Render"),
    ("review", "Review"),
    ("package", "Package"),
    ("validate", "Checks & status"),
    ("dev", "Pipeline development"),
    ("other", "Conversation & other"),
]
STEP_LABEL = dict(STEPS)

LOCAL_STAGE_STEP = {  # dashboard stage key or pipeline module → step
    "text_normalize": "text_normalize", "narration": "narration", "images": "images",
    "render_draft": "render", "render_final": "render", "render": "render",
    "review": "review", "review_draft": "review", "package": "package", "advance": "validate",
    "validate": "validate", "cast": "cast", "new_episode": "script", "tts_try": "dev", "broll": "other",
}
LOG_STAGE_STEP = {  # log.md headings of stages that do local compute
    "narration": "narration", "images": "images", "images (use earlier attempt)": "images",
    "render (draft)": "render", "render (final)": "render", "review": "review", "package": "package",
    "text_normalize": "text_normalize", "validate": "validate", "new_episode": "script",
}
SKILL_STEP = {"hindi-script": "script", "narration": "narration", "visuals": "images", "render": "render",
              "review": "review", "package": "package", "index-broll": "other", "make-episode": None}
MODULE_STEP = {"images": "images", "narration": "narration", "render": "render", "review": "review",
               "package": "package", "cast": "cast", "text_normalize": "text_normalize", "validate": "validate",
               "new_episode": "script", "tts_try": "dev", "broll": "other"}

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
DEV_PARTS = ("/pipeline/", "/remotion/", "/dashboard/", "/tests/", "/docs/", "/tts/", "/tts-mlx/", "/asr/",
             "/.claude/skills/", "/config.yaml", "/CLAUDE.md", "/PROJECT_BRIEF.md", "/pyproject.toml",
             "/pronunciation.yaml")
SHELL_RE = re.compile(r"^(\S*/)?(zsh|bash|sh|fish|dash)\s")   # a shell wrapping the command is not the run
EP_RE = re.compile(r"episodes/(\d{4}-\d\d-\d\d-[A-Za-z0-9._-]+?)(?=[/\s'\"]|$)")


def now() -> float:
    return time.time()


def load_costs() -> dict:
    try:
        from pipeline.common import load_config
        return load_config().get("costs") or {}
    except Exception:
        return {}


# ================================================================ Claude side

def classify_path(path: str) -> str | None:
    p = "/" + path.lstrip("/")
    if "/episodes/" in p:
        rel = p.split("/episodes/", 1)[1].split("/", 1)
        rel = rel[1] if len(rel) > 1 else ""
        if rel.startswith("images/") and rel.lower().endswith(IMAGE_EXT):
            return "image_inspection"
        if rel.startswith("review/"):
            return "review"
        if rel in ("script.md", "brief.md") or rel.startswith("sources/"):
            return "script"
        if rel == "youtube.md":
            return "package"
        if rel.startswith("audio/"):
            return "narration"
        if rel.startswith("render/"):
            return "render"
        return None   # episode.json etc.: belongs to whatever step is in progress
    if "/assets/cast/" in p:
        return "cast"
    if any(part in p for part in DEV_PARTS):
        return "dev"
    return None


def classify_tool(name: str, inp: dict) -> str | None:
    """Pipeline step a tool call belongs to; None = keep the session's current step."""
    if not isinstance(inp, dict):
        return None
    if name == "Skill":
        s = str(inp.get("skill", "")).split(":")[-1]
        return SKILL_STEP.get(s, "other") if s in SKILL_STEP else "other"
    if name == "Bash":
        cmd = str(inp.get("command", ""))
        m = re.search(r"pipeline\.(\w+)", cmd)
        if m:
            mod = m.group(1)
            if mod == "images" and ("--inspect" in cmd or "--crops" in cmd):
                return "image_inspection"
            return MODULE_STEP.get(mod, "other")
        if re.search(r"\bpytest\b|\btsc\b|remotion (still|studio)|\bgit (diff|commit|add|log|status)\b|\buv (sync|add)\b", cmd):
            return "dev"
        return None
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return classify_path(str(inp.get("file_path") or inp.get("notebook_path") or ""))
    if name in ("Grep", "Glob"):
        return classify_path(str(inp.get("path") or ""))
    return None


def message_cost(model: str, u: dict, costs: dict) -> float:
    prices = costs.get("claude_usd_per_mtok") or {}
    p = prices.get(model) or prices.get(costs.get("claude_default_model", "claude-opus-5-5")) or {}
    cc = u.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens")
    w5m = cc.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w5m, w1h = u.get("cache_creation_input_tokens") or 0, 0
    usd = ((u.get("input_tokens") or 0) * p.get("input", 0) + (u.get("output_tokens") or 0) * p.get("output", 0)
           + (u.get("cache_read_input_tokens") or 0) * p.get("cache_read", 0)
           + (w5m or 0) * p.get("cache_write_5m", 0) + (w1h or 0) * p.get("cache_write_1h", 0)) / 1e6
    web = ((u.get("server_tool_use") or {}).get("web_search_requests") or 0)
    return usd + web * costs.get("claude_web_search_usd_per_1k", 10.0) / 1000


class _FileState:
    def __init__(self) -> None:
        self.offset = 0
        self.step = "other"
        self.episode: str | None = None


class ClaudeUsage:
    """Incremental reader of Claude Code transcripts → one priced record per assistant message."""

    def __init__(self, transcripts_dir: Path = TRANSCRIPTS_DIR, episodes_dir: Path = EPISODES_DIR) -> None:
        self.dir, self.episodes_dir = transcripts_dir, episodes_dir
        self.files: dict[Path, _FileState] = {}
        self.recs: dict[str, dict] = {}       # message id → record
        self.lock = threading.Lock()
        self.loaded_at = 0.0
        self.ready = False
        self.costs = load_costs()

    def _known_episode(self, ep: str) -> bool:
        return (self.episodes_dir / ep / "episode.json").exists()

    def refresh(self, min_interval: float = 10.0) -> None:
        if now() - self.loaded_at < min_interval:
            return
        with self.lock:
            self.loaded_at = now()
            if not self.dir.exists():
                self.ready = True
                return
            for f in sorted(self.dir.rglob("*.jsonl")):
                if "memory" in f.parts:
                    continue
                st = self.files.setdefault(f, _FileState())
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                if size < st.offset:          # file rewritten: start over
                    st.offset = 0
                if size == st.offset:
                    continue
                with open(f, "rb") as fh:
                    fh.seek(st.offset)
                    data = fh.read(size - st.offset)
                end = data.rfind(b"\n")
                if end < 0:
                    continue
                for raw in data[:end].split(b"\n"):
                    if b'"assistant"' in raw:   # cheap pre-filter; json decides
                        self._line(raw, st, f.stem)
                st.offset += end + 1
            self.ready = True

    def _line(self, raw: bytes, st: _FileState, session: str) -> None:
        try:
            d = json.loads(raw)
        except ValueError:
            return
        if d.get("type") != "assistant":
            return
        m = d.get("message") or {}
        mid, model = m.get("id"), m.get("model")
        if not mid or not model or model.startswith("<"):
            return
        tools = [c for c in (m.get("content") or []) if isinstance(c, dict) and c.get("type") == "tool_use"]
        for c in tools:
            for ep in EP_RE.findall(json.dumps(c.get("input"), ensure_ascii=False)):
                if self._known_episode(ep):
                    st.episode = ep
            step = classify_tool(c.get("name", ""), c.get("input") or {})
            if step:
                st.step = step
        rec = self.recs.get(mid)
        if rec is None:
            rec = self.recs[mid] = {"ts": d.get("timestamp", ""), "session": session, "model": model,
                                    "step": st.step, "episode": st.episode, "sidechain": bool(d.get("isSidechain"))}
        elif tools:
            rec["step"], rec["episode"] = st.step, st.episode
        u = m.get("usage") or {}
        rec["usage"] = {k: u.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                     "cache_creation_input_tokens")}
        rec["usd"] = message_cost(model, u, self.costs)

    def records(self) -> list[dict]:
        with self.lock:
            out = []
            for r in self.recs.values():
                ep = None if r["step"] == "dev" else r["episode"]
                out.append({**r, "episode": ep})
            return out

    def live(self) -> dict:
        recs = self.records()
        if not recs:
            return {"active": False}
        t = now()
        def epoch(r):
            try:
                return datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0
        recent = [r for r in recs if t - epoch(r) < 600]
        last = max(recs, key=epoch)
        today = datetime.now().astimezone().date()
        usd_today = sum(r["usd"] for r in recs
                        if epoch(r) and datetime.fromtimestamp(epoch(r)).date() == today)
        return {"active": t - epoch(last) < 120, "last_ts": epoch(last), "step": last["step"],
                "step_label": STEP_LABEL.get(last["step"], last["step"]), "episode": last["episode"],
                "usd_10m": sum(r["usd"] for r in recent), "usd_today": usd_today}


# ================================================================ local side

def _cpu_seconds(s: str) -> float:
    """ps TIME ("1:02.34", "12:01:02.34" or "1-02:03:04") → seconds."""
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    total = 0.0
    for part in s.split(":"):
        total = total * 60 + float(part)
    return days * 86400 + total


def component(cmd: str) -> str:
    c = cmd.lower()
    if "mflux" in c:
        return "FLUX image model"
    if "asr_worker" in c or "whisper" in c:
        return "Whisper scoring"
    if any(w in c for w in ("mlx_worker", "snac_lm_worker", "indic_speak_worker", "parler_worker", "chatterbox")):
        return "TTS voice model"
    if "chrome" in c or "chromium" in c or "headless_shell" in c:
        return "Remotion browser (frames)"
    if "ffmpeg" in c or "ffprobe" in c:
        return "ffmpeg"
    if "node" in c or "remotion" in c or "npx" in c:
        return "Remotion (node)"
    if "-m pipeline." in c:
        return "pipeline (python)"
    return "other"


def ps_snapshot() -> list[dict]:
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,time=,rss=,%cpu=,command="], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return []
    procs = []
    for line in out.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        try:
            procs.append({"pid": int(parts[0]), "ppid": int(parts[1]), "cpu": _cpu_seconds(parts[2]),
                          "rss": int(parts[3]) * 1024, "pcpu": float(parts[4]), "cmd": parts[5]})
        except ValueError:
            continue
    return procs


def descendants(root: int, procs: list[dict]) -> set[int]:
    kids: dict[int, list[int]] = defaultdict(list)
    for p in procs:
        kids[p["ppid"]].append(p["pid"])
    seen, stack = {root}, [root]
    while stack:
        for c in kids.get(stack.pop(), []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def gpu_utilisation() -> float | None:
    try:
        out = subprocess.run(["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return None
    vals = [int(v) for v in re.findall(r'"Device Utilization %"\s*=\s*(\d+)', out)]
    return float(max(vals)) if vals else None


def system_power_w() -> float | None:
    """Whole-Mac power draw in W (battery telemetry; macOS updates it about once a minute)."""
    try:
        out = subprocess.run(["ioreg", "-r", "-w", "0", "-c", "AppleSmartBattery"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return None
    for key in ("SystemLoad", "SystemPowerIn"):
        m = re.search(r'"%s"\s*=\s*(\d+)' % key, out)
        if m and 0 < int(m.group(1)) < 500_000:
            return int(m.group(1)) / 1000
    return None


def describe_cmd(cmd: str) -> tuple[str, str | None, str]:
    """(stage, episode, label) for a terminal pipeline command."""
    m = re.search(r"-m (pipeline\.(\w+))(.*)", cmd)
    mod = m.group(2) if m else "pipeline"
    rest = m.group(3) if m else ""
    stage = mod
    if mod == "render":
        stage = "render_draft" if "--draft" in rest else "render_final"
    elif mod == "review" and "--draft" in rest:
        stage = "review_draft"
    e = EP_RE.search(cmd)
    args = rest.strip().replace(str(REPO_ROOT) + "/", "")
    args = re.split(r"['\"]", args)[0].strip()[:90]
    return stage, (e.group(1) if e else None), f"{mod} {args}".strip()


class _Run:
    def __init__(self, key: str, source: str, root: int, episode, stage, label) -> None:
        self.key, self.source, self.root = key, source, root
        self.episode, self.stage, self.label = episode, stage, label
        self.started = self.last = now()
        self.cpu_sec = self.gpu_sec = self.energy_j = 0.0
        self.peak_rss = 0
        self.pid_cpu: dict[int, float] = {}
        self.comp_cpu: dict[str, float] = defaultdict(float)
        self.samples: list[list[float]] = []   # [t_rel, cpu % of Mac, gpu %, W, rss MB]
        self.live: dict = {}

    def record(self) -> dict:
        wall = max(self.last - self.started, 0.0)
        s = self.samples
        if len(s) > 240:               # keep the file small: ≤ 240 points per run
            k = len(s) / 240
            s = [s[int(i * k)] for i in range(240)]
        return {"id": self.key, "source": self.source, "episode": self.episode, "stage": self.stage,
                "step": LOCAL_STAGE_STEP.get(self.stage, "other"), "label": self.label,
                "started": self.started, "ended": self.last, "wall_sec": round(wall, 1),
                "cpu_sec": round(self.cpu_sec, 1), "gpu_sec": round(self.gpu_sec, 1),
                "energy_wh": round(self.energy_j / 3600, 3), "peak_rss_mb": round(self.peak_rss / 1e6),
                "components": {k: round(v, 1) for k, v in sorted(self.comp_cpu.items(), key=lambda x: -x[1]) if v >= 0.05},
                "samples": s}


class Sampler:
    """Background sampler of pipeline processes. One instance, started by the server."""

    def __init__(self, runs_dir: Path, dashboard_job=None) -> None:
        self.path = runs_dir / "usage.jsonl"
        self.dashboard_job = dashboard_job or (lambda: None)   # → (job_id, pid, episode, stage, label) | None
        self.runs: dict[str, _Run] = {}
        self.lock = threading.Lock()
        self.ncpu = self._ncpu()
        self.gpu: float | None = None
        self.power: float | None = None
        self.idle_power: deque = deque(maxlen=60)
        self.last_t = now()
        self.sample_age = 0.0
        self._cache: tuple[float, list[dict]] = (0.0, [])

    @staticmethod
    def _ncpu() -> int:
        try:
            return int(subprocess.run(["sysctl", "-n", "hw.ncpu"], capture_output=True, text=True).stdout.strip())
        except Exception:
            return 8

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    # -- roots
    def _roots(self, procs: list[dict]) -> dict[str, tuple]:
        roots: dict[str, tuple] = {}
        dj = self.dashboard_job()
        mine: set[int] = set()
        if dj:
            jid, pid, ep, stage, label = dj
            roots["job:" + jid] = ("dashboard", pid, ep, stage, label)
            mine = descendants(pid, procs)
        me = os.getpid()   # the dashboard's own quick helpers (e.g. /api/validate) are not runs
        cand = [p for p in procs if re.search(r"-m pipeline\.\w+", p["cmd"]) and "dashboard" not in p["cmd"]
                and p["pid"] not in mine and p["ppid"] != me and not SHELL_RE.match(p["cmd"])]
        pids = {p["pid"] for p in cand}
        by_pid = {p["pid"]: p for p in procs}
        for p in cand:
            # top of each tree only (zsh -c → uv run → python …)
            anc, q, top = p["ppid"], 0, True
            while anc and q < 30:
                if anc in pids or "pytest" in by_pid.get(anc, {}).get("cmd", ""):   # tests' subprocesses aren't runs
                    top = False
                    break
                anc = by_pid.get(anc, {}).get("ppid", 0)
                q += 1
            if top:
                stage, ep, label = describe_cmd(p["cmd"])
                roots[f"term:{p['pid']}"] = ("terminal", p["pid"], ep, stage, label)
        return roots

    def _loop(self) -> None:
        tick = 0
        while True:
            try:
                busy = self._sample(tick)
            except Exception as e:   # never let metering kill the dashboard
                busy = False
                print(f"(usage sampler: {e})")
            tick += 1
            time.sleep(2.0 if busy else 5.0)

    def _sample(self, tick: int) -> bool:
        t = now()
        dt = min(t - self.last_t, 10.0)
        self.last_t = t
        procs = ps_snapshot()
        roots = self._roots(procs)
        self.gpu = gpu_utilisation()
        if roots or tick % 6 == 0:
            p = system_power_w()
            if p is not None:
                self.power = p
        if not roots and self.power is not None:
            self.idle_power.append(self.power)
        with self.lock:
            # close terminal runs that are gone (dashboard jobs are closed by finish())
            for key in [k for k in self.runs if k not in roots and k.startswith("term:")]:
                self._write(self.runs.pop(key).record())
            live_cpu = {}
            for key, (source, root, ep, stage, label) in roots.items():
                run = self.runs.get(key)
                if run is None:
                    run = self.runs[key] = _Run(key.split(":", 1)[1] if source == "dashboard" else
                                                f"t{datetime.now():%m%d-%H%M%S}-{root}", source, root, ep, stage, label)
                tree = descendants(root, procs)
                comp_live: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
                pcpu = rss = 0.0
                for p in procs:
                    if p["pid"] not in tree:
                        continue
                    prev = run.pid_cpu.get(p["pid"])
                    delta = p["cpu"] if prev is None else max(p["cpu"] - prev, 0.0)
                    run.pid_cpu[p["pid"]] = p["cpu"]
                    name = component(p["cmd"])
                    run.cpu_sec += delta
                    run.comp_cpu[name] += delta
                    comp_live[name][0] += p["pcpu"]
                    comp_live[name][1] += p["rss"]
                    pcpu += p["pcpu"]
                    rss += p["rss"]
                run.peak_rss = max(run.peak_rss, int(rss))
                run.last = t
                live_cpu[key] = pcpu
                run.live = {"cpu_pct": pcpu / self.ncpu, "cores": pcpu / 100, "rss_mb": rss / 1e6,
                            "components": sorted([{"name": n, "cpu_pct": v[0] / self.ncpu, "rss_mb": v[1] / 1e6}
                                                  for n, v in comp_live.items()], key=lambda c: -c["cpu_pct"])}
            total_cpu = sum(live_cpu.values()) or 1.0
            for key in roots:
                run = self.runs[key]
                share = (live_cpu[key] / total_cpu) if len(roots) > 1 else 1.0
                g = (self.gpu or 0.0) * share
                w = (self.power or 0.0) * share
                run.gpu_sec += g / 100 * dt
                run.energy_j += w * dt
                run.live.update({"gpu_pct": g, "power_w": w})
                run.samples.append([round(t - run.started, 1), round(run.live["cpu_pct"], 1), round(g, 1),
                                    round(w, 2), round(run.live["rss_mb"])])
        return bool(roots)

    def finish(self, job_id: str, ended: float, cpu_exact: float | None, maxrss: int | None,
               meta: tuple | None = None) -> None:
        """Called by the job runner when a dashboard job exits (exact rusage from wait4)."""
        with self.lock:
            run = self.runs.pop("job:" + job_id, None)
            if run is None and meta:          # too short for the sampler to have seen it
                ep, stage, label, started = meta
                run = _Run(job_id, "dashboard", 0, ep, stage, label)
                run.started = started
            if run is None:
                return
            run.last = ended
            if cpu_exact is not None:
                sampled = run.cpu_sec
                if sampled > 0:
                    k = cpu_exact / sampled
                    for n in run.comp_cpu:
                        run.comp_cpu[n] *= k
                else:
                    run.comp_cpu["pipeline (python)"] += cpu_exact
                run.cpu_sec = cpu_exact
            if maxrss:
                run.peak_rss = max(run.peak_rss, maxrss)
            self._write(run.record())

    def _write(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def live(self) -> dict:
        with self.lock:
            runs = [{"id": r.key, "source": r.source, "label": r.label, "episode": r.episode, "stage": r.stage,
                     "step": LOCAL_STAGE_STEP.get(r.stage, "other"), "elapsed": now() - r.started, **r.live,
                     "so_far": {"cpu_sec": r.cpu_sec, "gpu_sec": r.gpu_sec, "energy_wh": r.energy_j / 3600}}
                    for r in self.runs.values()]
        idle = statistics.median(self.idle_power) if self.idle_power else None
        return {"runs": runs, "system": {"gpu_pct": self.gpu, "power_w": self.power, "idle_w": idle,
                                         "ncpu": self.ncpu}}

    def history(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out


# ================================================================ aggregation for /api/usage

def aggregate(claude: ClaudeUsage, sampler: Sampler, parse_log, episode: str | None = None) -> dict:
    costs = claude.costs or load_costs()
    usd_inr = float(costs.get("usd_to_inr", 88))
    inr_kwh = float(costs.get("electricity_inr_per_kwh", 8))

    # Claude
    recs = claude.records()
    if episode:
        recs = [r for r in recs if r["episode"] == episode]
    c_step: dict[str, float] = defaultdict(float)
    c_ep: dict[str, float] = defaultdict(float)
    c_day: dict[str, float] = defaultdict(float)
    c_msgs: dict[str, int] = defaultdict(int)
    tok = defaultdict(int)
    for r in recs:
        c_step[r["step"]] += r["usd"]
        c_msgs[r["step"]] += 1
        c_ep[r["episode"] or "(no episode)"] += r["usd"]
        c_day[(r["ts"] or "")[:10]] += r["usd"]
        for k, v in r["usage"].items():
            tok[k] += v
    c_total = sum(c_step.values())

    # local, metered
    runs = sampler.history()
    if episode:
        runs = [r for r in runs if r.get("episode") == episode]
    l_step: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    l_ep: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    comps: dict[str, float] = defaultdict(float)
    for r in runs:
        for agg in (l_step[r.get("step", "other")], l_ep[r.get("episode") or "(no episode)"]):
            for k in ("wall_sec", "cpu_sec", "gpu_sec", "energy_wh"):
                agg[k] += r.get(k) or 0
            agg["runs"] += 1
        for n, v in (r.get("components") or {}).items():
            comps[n] += v
    m_tot = {k: sum(r.get(k) or 0 for r in runs) for k in ("wall_sec", "cpu_sec", "gpu_sec", "energy_wh")}

    # local, wall time from every episode's log.md (also covers runs before metering existed)
    g_step: dict[str, float] = defaultdict(float)
    g_ep: dict[str, float] = defaultdict(float)
    dirs = [EPISODES_DIR / episode] if episode else sorted(d for d in EPISODES_DIR.iterdir() if d.is_dir())
    for d in dirs:
        for e in parse_log(d / "log.md"):
            step = LOG_STAGE_STEP.get(e["stage"])
            if step and e["duration"]:
                g_step[step] += e["duration"]
                g_ep[d.name] += e["duration"]

    def step_rows():
        rows = []
        for key, label in STEPS:
            row = {"key": key, "label": label, "claude_usd": c_step.get(key, 0.0), "claude_msgs": c_msgs.get(key, 0),
                   "logged_wall_sec": g_step.get(key, 0.0), "metered": dict(l_step[key]) if key in l_step else None}
            if row["claude_usd"] or row["logged_wall_sec"] or row["metered"]:
                rows.append(row)
        return rows

    eps = sorted(set(c_ep) | set(g_ep) | set(l_ep))
    ep_rows = [{"episode": e, "claude_usd": c_ep.get(e, 0.0), "logged_wall_sec": g_ep.get(e, 0.0),
                "metered": dict(l_ep[e]) if e in l_ep else None,
                "test": "phase5-test" in e} for e in eps]
    ep_rows.sort(key=lambda r: -(r["claude_usd"] + r["logged_wall_sec"] / 3600))

    recent = sorted(runs, key=lambda r: -(r.get("started") or 0))[:25]
    energy_inr = m_tot["energy_wh"] / 1000 * inr_kwh
    return {
        "episode": episode, "ready": claude.ready,
        "claude": {"usd": c_total, "inr": c_total * usd_inr, "messages": len(recs), "tokens": dict(tok),
                   "by_day": dict(sorted(c_day.items()))},
        "local": {"metered": {**m_tot, "runs": len(runs), "inr": energy_inr,
                              "components": dict(sorted(comps.items(), key=lambda x: -x[1]))},
                  "logged_wall_sec": sum(g_step.values()),
                  "metering_since": min((r.get("started") or 0 for r in sampler.history()), default=None)},
        "steps": step_rows(), "episodes": ep_rows if not episode else [], "recent_runs": recent,
        "rates": {"usd_to_inr": usd_inr, "electricity_inr_per_kwh": inr_kwh,
                  "idle_w": sampler.live()["system"]["idle_w"]},
        "notes": {
            "claude": "API list price of the tokens in this project's Claude Code transcripts (config.yaml "
                      "costs.claude_usd_per_mtok). On a Claude subscription you pay the flat plan fee; this "
                      "is what the same work would cost through the API.",
            "local": "Measured by the dashboard while it runs: CPU time per process, Apple GPU busy %, whole-Mac "
                     "power from the battery telemetry (refreshes about once a minute, so short runs are rough).",
            "logged": "Stage durations from each episode's log.md, including runs from before metering started.",
        },
    }
