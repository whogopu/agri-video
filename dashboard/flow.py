"""Pipeline flow: the episode as a Jenkins-style stage graph, showing WHERE each step executes.

Every stage is a column of steps. Each step says what runs it, read from config.yaml so it stays
true when a backend changes:
  gpu    — a model running on this Mac's GPU (MLX / Metal): TTS voice, Whisper, FLUX, local VLM
  cpu    — this Mac's CPU: Python, ffmpeg, Remotion's headless Chrome
  api    — a call to a cloud service: Claude (Anthropic API) today; a cloud TTS / image backend later
  human  — you, at a checkpoint
For each step it attaches what was measured for this episode: CPU seconds of that process group
(dashboard/runs/usage.jsonl), Claude $ for that step (transcripts), and the stage's logged time (log.md).
While something runs, the steps whose processes are busy right now are marked active.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from dashboard import usage

# Backends that run on this Mac. Anything else in config.yaml is treated as a cloud API call,
# so a future `tts.voices.<v>.backend: elevenlabs` shows up as "Cloud API" with no code change here.
LOCAL_GPU_BACKENDS = {"mlx_audio", "parler", "mflux", "whisper", "mlx_vlm", "mlx"}
KINDS = {
    "gpu": {"label": "This Mac · GPU", "hint": "model running locally on Apple GPU (MLX / Metal)"},
    "cpu": {"label": "This Mac · CPU", "hint": "Python, ffmpeg, Remotion's headless Chrome"},
    "api": {"label": "Cloud API", "hint": "a server call, billed per use (Claude today)"},
    "human": {"label": "You", "hint": "human checkpoint: nothing moves until you approve"},
}


def _kind(backend: str | None) -> str:
    return "gpu" if (backend or "") in LOCAL_GPU_BACKENDS else "api"


def _short(model: str | None) -> str:
    return (model or "").split("/")[-1]


def _claude_engine(recs: list[dict], step: str, default: str) -> str:
    models = Counter(r["model"] for r in recs if r["step"] == step)
    m = models.most_common(1)[0][0] if models else default
    return f"{m} · Anthropic API (via Claude Code)"


def _step(label, kind, where, engine, components=(), claude_step=None, note=""):
    return {"label": label, "kind": kind, "where": where, "engine": engine, "components": list(components),
            "claude_step": claude_step, "note": note}


def stage_defs(cfg: dict, ep: dict, recs: list[dict]) -> list[dict]:
    """The flow, with each step's executor resolved from config.yaml and the episode's voice."""
    tts = cfg.get("tts") or {}
    preset = (ep.get("voice") or {}).get("preset") or tts.get("default_voice")
    voice = (tts.get("voices") or {}).get(preset) or {}
    v_backend = voice.get("backend") or tts.get("backend")
    v_model = voice.get("model") or tts.get("model")
    v_worker = voice.get("worker")
    asr = (cfg.get("narration") or {}).get("asr") or {}
    img = cfg.get("images") or {}
    vlm = img.get("vlm_inspect")
    rnd = cfg.get("render") or {}
    claude_default = (cfg.get("costs") or {}).get("claude_default_model", "claude")
    cl = lambda step: _claude_engine(recs, step, claude_default)  # noqa: E731
    hw = rnd.get("hardware_acceleration")
    encode = f"H.264 · VideoToolbox ({hw})" if hw and hw != "disable" else "H.264 · software"

    def render_steps():
        return [
            _step("Bundle compositions", "cpu", "This Mac · Node", "Remotion 4.0.545 (webpack)", ["Remotion (node)"]),
            _step("Draw frames", "cpu", "This Mac · headless Chrome",
                  f"Remotion · concurrency {rnd.get('concurrency', '?')}", ["Remotion browser (frames)"]),
            _step("Encode video + audio", "cpu", "This Mac · ffmpeg", encode, ["ffmpeg"]),
        ]

    has_cast = bool(ep.get("cast")) or any(
        sh.get("characters") for s in ep.get("scenes", []) for sh in ((s.get("visual") or {}).get("shots") or []))
    img_steps = [
        _step("Generate stills, one per shot", _kind(img.get("backend")), "This Mac · GPU"
              if _kind(img.get("backend")) == "gpu" else "Cloud API",
              f"{_short(img.get('model'))} · {img.get('command', img.get('backend'))} · {img.get('steps', '?')} steps",
              ["FLUX image model"]),
    ]
    if has_cast:
        img_steps.append(_step("Cast shots: edit from approved face", _kind(img.get("backend")), "This Mac · GPU",
                               f"{img.get('edit_command', 'edit mode')} + reference image", [],
                               note="measured together with stills"))
    img_steps.append(_step("Zoomed crops for inspection", "cpu", "This Mac · Python", "Pillow",
                           ["pipeline (python)"]))

    insp_steps = [_step("Check every image (hands, physics, identity, text)", "api", "Cloud API", cl("image_inspection"),
                        claude_step="image_inspection")]
    if vlm:
        insp_steps.append(_step("Pre-screen (trial, advisory only)", "gpu", "This Mac · GPU",
                                f"{_short(vlm.get('model'))} · mlx-vlm", [], note="manual trial runs; not metered"))

    tts_kind = _kind(v_backend)
    return [
        {"key": "script", "label": "Script & research", "run": None, "log": ["new_episode"],
         "steps": [_step("Read sources, write Hindi script", "api", "Cloud API", cl("script"), claude_step="script"),
                   _step("Fact gate: no [VERIFY] left", "cpu", "This Mac · Python", "pipeline.validate",
                         ["pipeline (python)"])]},
        {"key": "cp1", "label": "Checkpoint 1", "checkpoint": "script_approved", "what": "you approve the script"},
        {"key": "text_normalize", "label": "Spoken text", "run": "text_normalize", "log": ["text_normalize"],
         "steps": [_step("Numbers → words, pronunciation fixes", "cpu", "This Mac · Python",
                         "pipeline.text_normalize + pronunciation.yaml", ["pipeline (python)"])]},
        {"key": "narration", "label": "Narration", "run": "narration", "log": ["narration"],
         "steps": [_step(f"TTS takes per sentence ({preset})", tts_kind,
                         "This Mac · GPU" if tts_kind == "gpu" else "Cloud API",
                         f"{_short(v_model)} · {v_worker or v_backend}", ["TTS voice model"]),
                   _step("Score takes, pick best", _kind(asr.get("backend")), "This Mac · GPU",
                         f"{_short(asr.get('model'))} · mlx-whisper", ["Whisper scoring"]),
                   _step("Word timing for captions", _kind(asr.get("backend")), "This Mac · GPU",
                         f"{_short(asr.get('model'))} + script alignment", [], note="measured with scoring"),
                   _step("Trim, loudness, room tone", "cpu", "This Mac · ffmpeg", "ffmpeg loudnorm",
                         ["ffmpeg"])]},
        {"key": "images", "label": "Images", "run": "images", "log": ["images", "images (use earlier attempt)"],
         "steps": img_steps},
        {"key": "inspection", "label": "Image inspection", "run": None, "log": ["image inspection"],
         "steps": insp_steps},
        {"key": "render_draft", "label": "Draft render", "run": "render_draft", "log": ["render (draft)"],
         "steps": render_steps()},
        {"key": "cp2", "label": "Checkpoint 2", "checkpoint": "final_rendered", "what": "you approve the draft"},
        {"key": "render_final", "label": "Final render", "run": "render_final", "log": ["render (final)"],
         "steps": render_steps()},
        {"key": "review", "label": "Review", "run": "review", "log": ["review"],
         "steps": [_step("Contact sheets, loudness, black/freeze", "cpu", "This Mac · ffmpeg + Pillow",
                         "ffmpeg ebur128 / blackdetect · Pillow", ["ffmpeg", "pipeline (python)"]),
                   _step("Look at sheets, write review.md", "api", "Cloud API", cl("review"), claude_step="review")]},
        {"key": "package", "label": "Package", "run": "package", "log": ["package"],
         "steps": [_step("Title, description, tags", "api", "Cloud API", cl("package"), claude_step="package"),
                   _step("Thumbnail still", "cpu", "This Mac · headless Chrome", "Remotion still",
                         ["Remotion (node)", "Remotion browser (frames)"])]},
        {"key": "cp3", "label": "Checkpoint 3", "checkpoint": "packaged", "what": "you approve video + package"},
    ]


# dashboard / terminal run stage → flow column
RUN_COLUMN = {"text_normalize": "text_normalize", "narration": "narration", "images": "images",
              "render_draft": "render_draft", "render_final": "render_final", "review": "review",
              "review_draft": "review", "package": "package", "new_episode": "script", "validate": "script"}
CLAUDE_COLUMN = {"script": "script", "narration": "narration", "images": "images",
                 "image_inspection": "inspection", "render": None, "review": "review", "package": "package",
                 "text_normalize": "text_normalize"}


def build(ep_id: str, ep: dict, detail: dict, cfg: dict, claude: usage.ClaudeUsage | None,
          sampler: usage.Sampler | None, parse_log, log_path, running_job: dict | None) -> dict:
    costs = cfg.get("costs") or {}
    usd_inr = float(costs.get("usd_to_inr", 88))
    inr_kwh = float(costs.get("electricity_inr_per_kwh", 8))
    recs = [r for r in (claude.records() if claude and claude.ready else []) if r["episode"] == ep_id]
    defs = stage_defs(cfg, ep, recs)
    rank = detail["statuses"].index(detail["status"]) if detail["status"] in detail["statuses"] else 0
    stage_state = {s["key"]: s["state"] for s in detail["stages"]}
    counts = detail["counts"]

    # Claude $ by step for this episode
    c_usd: dict[str, float] = defaultdict(float)
    c_msgs: dict[str, int] = defaultdict(int)
    for r in recs:
        c_usd[r["step"]] += r["usd"]
        c_msgs[r["step"]] += 1

    # metered local runs for this episode, by column: components CPU, energy, wall
    m_col: dict[str, dict] = defaultdict(lambda: {"cpu_sec": 0.0, "gpu_sec": 0.0, "energy_wh": 0.0, "wall_sec": 0.0,
                                                  "runs": 0, "components": defaultdict(float)})
    for r in (sampler.history() if sampler else []):
        if r.get("episode") != ep_id:
            continue
        col = RUN_COLUMN.get(r.get("stage"))
        if not col:
            continue
        m = m_col[col]
        for k in ("cpu_sec", "gpu_sec", "energy_wh", "wall_sec"):
            m[k] += r.get(k) or 0
        m["runs"] += 1
        for n, v in (r.get("components") or {}).items():
            m["components"][n] += v

    # logged wall time (log.md), all runs
    log = parse_log(log_path)
    l_sum: dict[str, float] = defaultdict(float)
    l_runs: dict[str, int] = defaultdict(int)
    l_last: dict[str, dict] = {}
    for e in log:
        l_sum[e["stage"]] += e["duration"] or 0
        l_runs[e["stage"]] += 1
        l_last[e["stage"]] = e

    # live: what is busy right now
    live = sampler.live() if sampler else {"runs": [], "system": {}}
    live_col: dict[str, dict] = {}
    for r in live.get("runs", []):
        if r.get("episode") == ep_id and RUN_COLUMN.get(r.get("stage")):
            live_col[RUN_COLUMN[r["stage"]]] = r
    if running_job and running_job.get("episode") == ep_id and RUN_COLUMN.get(running_job.get("stage")):
        live_col.setdefault(RUN_COLUMN[running_job["stage"]], {"components": []})
    cl_live = claude.live() if claude and claude.ready else {"active": False}
    claude_col = CLAUDE_COLUMN.get(cl_live.get("step")) if cl_live.get("active") and cl_live.get(
        "episode") == ep_id else None

    out = []
    for d in defs:
        if d.get("checkpoint"):
            target = detail["statuses"].index(d["checkpoint"])
            state = "done" if rank >= target else ("waiting" if rank == target - 1 else "blocked")
            if d["key"] == "cp1" and state == "waiting" and counts.get("verify"):
                state = "blocked"
            out.append({"key": d["key"], "label": d["label"], "checkpoint": True, "what": d["what"], "state": state})
            continue
        key = d["key"]
        m = m_col.get(key)
        lv = live_col.get(key)
        live_comps = {c["name"]: c for c in (lv or {}).get("components", []) if c.get("cpu_pct", 0) >= 0.3}
        steps = []
        claude_steps = set()
        for s in d["steps"]:
            cpu = sum(m["components"].get(c, 0.0) for c in s["components"]) if m else 0.0
            usd_ = c_usd.get(s["claude_step"], 0.0) if s["claude_step"] else 0.0
            if s["claude_step"]:
                claude_steps.add(s["claude_step"])
            active = bool(lv and any(c in live_comps for c in s["components"])) or (
                s["kind"] == "api" and claude_col == key)
            lc = [live_comps[c] for c in s["components"] if c in live_comps]
            steps.append({**{k: s[k] for k in ("label", "kind", "where", "engine", "note")},
                          "cpu_sec": cpu, "claude_usd": usd_, "claude_msgs": c_msgs.get(s["claude_step"], 0)
                          if s["claude_step"] else 0, "active": active,
                          "live": {"cpu_pct": sum(c["cpu_pct"] for c in lc), "rss_mb": sum(c["rss_mb"] for c in lc)}
                          if lc else None})
        # Claude also helps in stages that are mostly local (picks takes, rewrites prompts…): show it
        own = {"narration": "narration", "images": "images", "text_normalize": "text_normalize",
               "render_draft": None, "render_final": None}.get(key)
        if own and own not in claude_steps and c_usd.get(own, 0) > 0:
            steps.append({"label": "Claude: run, check, fix prompts", "kind": "api", "where": "Cloud API",
                          "engine": _claude_engine(recs, own, (cfg.get("costs") or {}).get("claude_default_model", "")),
                          "note": "", "cpu_sec": 0.0, "claude_usd": c_usd[own], "claude_msgs": c_msgs[own],
                          "active": claude_col == key, "live": None})
            claude_steps.add(own)
        if key == "render_draft":   # Claude's render work is not split draft/final: show it once
            r_usd = c_usd.get("render", 0.0)
            if r_usd > 0:
                steps.append({"label": "Claude: run, check output", "kind": "api", "where": "Cloud API",
                              "engine": _claude_engine(recs, "render", ""), "note": "draft + final", "cpu_sec": 0.0,
                              "claude_usd": r_usd, "claude_msgs": c_msgs["render"], "active": False, "live": None})
                claude_steps.add("render")

        wall = sum(l_sum.get(n, 0.0) for n in d["log"])
        runs = sum(l_runs.get(n, 0) for n in d["log"])
        last = max((l_last[n] for n in d["log"] if n in l_last), key=lambda e: e["started"], default=None)
        claude_usd = sum(c_usd.get(s, 0.0) for s in claude_steps)
        energy = m["energy_wh"] if m else 0.0

        # state
        if lv or (claude_col == key):
            state = "running"
        elif key == "script":
            state = "done" if rank >= 1 or ("script.md" in detail["files"] and not counts.get("verify")) else (
                "warn" if counts.get("verify") else "ready")
        elif key == "inspection":
            n, ok = counts.get("shots", 0), counts.get("inspected_pass", 0)
            state = "done" if n and ok == n else ("ready" if rank >= 2 and n else "blocked")
        elif key == "review":
            state = stage_state.get("review", "blocked")
            if state != "done" and stage_state.get("review_draft") == "done" and rank < 5:
                state = "partial"
        else:
            state = stage_state.get(key, "blocked")
        progress = None
        if key == "inspection" and counts.get("shots"):
            progress = {"done": counts.get("inspected_pass", 0), "total": counts["shots"], "unit": "passed"}
        if key == "narration" and counts.get("scenes"):
            progress = {"done": counts.get("audio", 0), "total": counts["scenes"], "unit": "scenes voiced"}
        if key == "images" and counts.get("shots"):
            progress = {"done": sum(1 for s in detail["scenes"] for sh in s["shots"] if sh["exists"]),
                        "total": counts["shots"], "unit": "images"}

        out.append({"key": key, "label": d["label"], "run": d["run"], "state": state, "steps": steps,
                    "progress": progress,
                    "live": {k: lv.get(k) for k in ("cpu_pct", "gpu_pct", "power_w", "rss_mb", "elapsed")} if lv else None,
                    "metrics": {"wall_sec": wall, "runs": runs, "last": last, "claude_usd": claude_usd,
                                "energy_wh": energy, "cpu_sec": m["cpu_sec"] if m else 0.0,
                                "gpu_sec": m["gpu_sec"] if m else 0.0, "metered_runs": m["runs"] if m else 0,
                                "cost_inr": claude_usd * usd_inr + energy / 1000 * inr_kwh}})

    stages = [s for s in out if not s.get("checkpoint")]
    tot_inr = sum(s["metrics"]["cost_inr"] for s in stages)
    tot_wall = sum(s["metrics"]["wall_sec"] for s in stages)
    for s in stages:
        s["metrics"]["cost_share"] = s["metrics"]["cost_inr"] / tot_inr if tot_inr else 0
        s["metrics"]["time_share"] = s["metrics"]["wall_sec"] / tot_wall if tot_wall else 0
    top_cost = max(stages, key=lambda s: s["metrics"]["cost_inr"], default=None)
    top_time = max(stages, key=lambda s: s["metrics"]["wall_sec"], default=None)
    other_claude = sum(v for k, v in c_usd.items() if k not in {"script", "narration", "images", "image_inspection",
                                                                  "render", "review", "package", "text_normalize"})
    return {"episode": ep_id, "stages": out, "kinds": KINDS,
            "totals": {"cost_inr": tot_inr, "wall_sec": tot_wall,
                       "claude_usd": sum(s["metrics"]["claude_usd"] for s in stages),
                       "energy_wh": sum(s["metrics"]["energy_wh"] for s in stages),
                       "other_claude_usd": other_claude, "usd_to_inr": usd_inr,
                       "top_cost": top_cost["key"] if top_cost and top_cost["metrics"]["cost_inr"] > 0 else None,
                       "top_time": top_time["key"] if top_time and top_time["metrics"]["wall_sec"] > 0 else None},
            "system": live.get("system", {}), "claude_live": cl_live if claude_col else None}
