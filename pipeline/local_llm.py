"""Text-only local LLM calls through the vlm/ env (mlx-vlm), used by pipeline/shot_specs.py.

The cached vision-language models (Ministral 3 14B, Qwen3.5 9B) answer text-only jobs when a job has no
images, so no separate llm/ env is needed (plan P2, 2026-11-22). vlm/vlm_worker.py takes one `prompt` per
job, so `system` and `prompt` are joined here. The model loads once per call (2–8 s).

Heavy job: waits while FLUX, TTS, Whisper, a render or another VLM run is busy (16 GB Mac, one at a time).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pipeline.common import REPO_ROOT

VLM_PROJECT = REPO_ROOT / "vlm"


def wait_for_quiet(poll: float = 20.0) -> None:
    from pipeline.bakeoff import other_heavy_jobs
    said = False
    while jobs := other_heavy_jobs():
        if not said:
            print(f"local LLM: waiting, another heavy job is running ({jobs[0]})", file=sys.stderr, flush=True)
            said = True
        time.sleep(poll)


def generate(jobs: list[dict[str, str]], model: str, max_tokens: int = 1800, temperature: float = 0.2,
             log: Path | None = None) -> dict[str, dict[str, Any]]:
    """jobs: [{id, system, prompt}] → {id: {text, sec, prompt_tokens, gen_tokens, peak_mem_gb} | {error}}."""
    if not jobs:
        return {}
    wait_for_quiet()
    req = {"model": model, "max_tokens": int(max_tokens), "temperature": float(temperature),
           "enable_thinking": False,
           "jobs": [{"id": j["id"], "images": [],
                     "prompt": (j.get("system", "").strip() + "\n\n" + j["prompt"]).strip()} for j in jobs]}
    cmd = ["uv", "run", "--project", str(VLM_PROJECT), "python", str(VLM_PROJECT / "vlm_worker.py")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None, text=True)
    assert proc.stdin and proc.stdout
    proc.stdin.write(json.dumps(req, ensure_ascii=False))
    proc.stdin.close()
    out: dict[str, dict[str, Any]] = {}
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("{"):
            r = json.loads(line)
            out[r["id"]] = r
            if log:
                with open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({**r, "model": model}, ensure_ascii=False) + "\n")
    if proc.wait() != 0:
        raise RuntimeError(f"local LLM worker failed (exit {proc.returncode}); see messages above")
    return out
