"""dashboard/flow.py: executors come from config, live processes mark steps active, checkpoints gate."""

from dashboard import flow

STATUSES = ["draft", "script_approved", "narrated", "visuals_ready", "draft_rendered",
            "final_rendered", "reviewed", "packaged"]

CFG = {
    "tts": {"default_voice": "v", "voices": {"v": {"backend": "mlx_audio", "model": "maya-research/maya2-native"},
                                            "cloud": {"backend": "elevenlabs", "model": "eleven_multilingual_v2"}}},
    "narration": {"asr": {"backend": "whisper", "model": "mlx-community/whisper-large-v3-turbo"}},
    "images": {"backend": "mflux", "model": "x/flux2-klein", "command": "mflux-generate-flux2", "steps": 4},
    "render": {"concurrency": 4, "hardware_acceleration": "if-possible"},
    "costs": {"claude_default_model": "claude-opus-5-5", "usd_to_inr": 88, "electricity_inr_per_kwh": 8},
}


def _detail(status="narrated"):
    return {"statuses": STATUSES, "status": status, "files": {"script.md": {}},
            "counts": {"shots": 2, "inspected_pass": 0, "audio": 3, "scenes": 3, "verify": 0},
            "scenes": [{"shots": [{"exists": True}, {"exists": False}]}],
            "stages": [{"key": k, "state": "ready"} for k in
                       ("text_normalize", "narration", "images", "render_draft", "review_draft", "render_final",
                        "review", "package")]}


class FakeClaude:
    ready = True

    def __init__(self, recs, live=None):
        self._recs, self._live = recs, live or {"active": False}

    def records(self):
        return self._recs

    def live(self):
        return self._live


class FakeSampler:
    def __init__(self, hist=(), live_runs=()):
        self._h, self._l = list(hist), list(live_runs)

    def history(self):
        return self._h

    def live(self):
        return {"runs": self._l, "system": {}}


def _build(ep=None, claude=None, sampler=None, status="narrated", cfg=CFG):
    return flow.build("ep1", ep or {"voice": {"preset": "v"}, "scenes": []}, _detail(status), cfg,
                      claude or FakeClaude([]), sampler or FakeSampler(), lambda p: [], "log.md", None)


def _col(d, key):
    return next(s for s in d["stages"] if s["key"] == key)


def test_executor_kind_follows_config_backend():
    tts = _col(_build(), "narration")["steps"][0]
    assert tts["kind"] == "gpu" and "maya2-native" in tts["engine"]
    cloud = _col(_build(ep={"voice": {"preset": "cloud"}, "scenes": []}), "narration")["steps"][0]
    assert cloud["kind"] == "api"          # a non-local backend shows as a cloud call, no code change
    assert _col(_build(), "images")["steps"][0]["kind"] == "gpu"
    assert all(s["kind"] == "cpu" for s in _col(_build(), "render_draft")["steps"])


def test_measured_cpu_and_claude_cost_land_on_steps():
    hist = [{"episode": "ep1", "stage": "narration", "cpu_sec": 100, "gpu_sec": 50, "energy_wh": 2.0,
             "wall_sec": 60, "components": {"TTS voice model": 70, "Whisper scoring": 20, "ffmpeg": 10}},
            {"episode": "other", "stage": "narration", "cpu_sec": 999, "components": {"TTS voice model": 999}}]
    recs = [{"episode": "ep1", "step": "image_inspection", "usd": 1.5, "model": "claude-opus-5-5"},
            {"episode": "ep1", "step": "narration", "usd": 0.5, "model": "claude-opus-5-5"}]
    d = _build(claude=FakeClaude(recs), sampler=FakeSampler(hist))
    nar = _col(d, "narration")
    assert [s["cpu_sec"] for s in nar["steps"][:4]] == [70, 20, 0, 10]
    assert nar["steps"][-1]["kind"] == "api" and nar["steps"][-1]["claude_usd"] == 0.5   # Claude helper step
    assert _col(d, "inspection")["steps"][0]["claude_usd"] == 1.5
    assert d["totals"]["top_cost"] == "inspection"
    assert abs(nar["metrics"]["cost_inr"] - (0.5 * 88 + 2.0 / 1000 * 8)) < 1e-9


def test_live_processes_mark_active_steps():
    live = [{"episode": "ep1", "stage": "images", "cpu_pct": 30, "gpu_pct": 95, "power_w": 12, "rss_mb": 3000,
             "elapsed": 10, "components": [{"name": "FLUX image model", "cpu_pct": 25, "rss_mb": 2900},
                                           {"name": "pipeline (python)", "cpu_pct": 0.1, "rss_mb": 100}]}]
    d = _build(sampler=FakeSampler(live_runs=live))
    img = _col(d, "images")
    assert img["state"] == "running"
    assert img["steps"][0]["active"] and img["steps"][0]["live"]["cpu_pct"] == 25
    assert not img["steps"][-1]["active"]          # python below threshold
    d = _build(claude=FakeClaude([], {"active": True, "step": "image_inspection", "episode": "ep1"}))
    assert _col(d, "inspection")["state"] == "running" and _col(d, "inspection")["steps"][0]["active"]


def test_checkpoints():
    d = _build(status="script_approved")
    assert _col(d, "cp1")["state"] == "done"
    assert _col(d, "cp2")["state"] == "blocked"
    d = _build(status="draft_rendered")
    assert _col(d, "cp2")["state"] == "waiting"
