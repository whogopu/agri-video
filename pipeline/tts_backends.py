"""TTS backends. Contract: synthesize(text, voice_cfg, out_path) -> duration_sec.

Backends may also implement synthesize_many() to load a model once for many jobs
(all real ones do). parler: Indic Parler-TTS (tts/ env). mlx_audio: any mlx-audio model,
e.g. Maya2 Native or Chatterbox Multilingual (tts-mlx/ env). Add ElevenLabs / Sarvam / IndicF5 here and select via config.yaml `tts.backend`.
Output of a backend is a raw WAV at any sample rate; narration.py post-processes it.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.audio import duration as wav_duration
from pipeline.audio import run as run_cmd
from pipeline.common import REPO_ROOT, log


@dataclass
class TTSJob:
    text: str
    out: Path
    description: str | None = None  # per-job delivery style; default: the voice description
    seed: int | None = None         # per-job seed (takes); default: the voice seed
    params: dict | None = None      # per-job model-specific generate() options (style), mlx backends


@dataclass
class TTSResult:
    out: Path
    sec_audio: float
    sec_compute: float
    device: str = ""


def voice_description(voice_cfg: dict[str, Any]) -> str:
    """config `description` may contain {speaker}."""
    return str(voice_cfg.get("description", "")).format(speaker=voice_cfg.get("speaker", ""))


class TTSBackend:
    name = "base"

    def synthesize_many(self, jobs: list[TTSJob], voice_cfg: dict[str, Any]) -> list[TTSResult]:
        raise NotImplementedError

    def synthesize(self, text: str, voice_cfg: dict[str, Any], out_path: Path) -> float:
        return self.synthesize_many([TTSJob(text, out_path)], voice_cfg)[0].sec_audio


class ParlerBackend(TTSBackend):
    """AI4Bharat Indic Parler-TTS, run in the isolated tts/ env as a subprocess."""

    name = "parler"
    TTS_PROJECT = REPO_ROOT / "tts"

    def synthesize_many(self, jobs, voice_cfg):
        desc = voice_description(voice_cfg)
        req = {
            "model": voice_cfg.get("model", "ai4bharat/indic-parler-tts"),
            "device": voice_cfg.get("device", "mps"),
            "seed": int(voice_cfg.get("seed", 42)),
            "jobs": [{"text": j.text, "description": j.description or desc, "out": str(j.out),
                      **({"seed": j.seed} if j.seed is not None else {})} for j in jobs],
        }
        for j in jobs:
            j.out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["uv", "run", "--project", str(self.TTS_PROJECT), "python", str(self.TTS_PROJECT / "parler_worker.py")]
        log.info("parler: %d job(s), speaker=%s, device=%s", len(jobs), voice_cfg.get("speaker"), req["device"])
        env = {**os.environ, "TOKENIZERS_PARALLELISM": "false"}
        # stderr streams through so model-loading progress is visible
        proc = subprocess.run(cmd, input=json.dumps(req, ensure_ascii=False), stdout=subprocess.PIPE,
                              stderr=None, text=True, env=env)
        if proc.returncode != 0:
            raise RuntimeError(f"parler worker failed (exit {proc.returncode}); see messages above")
        results = []
        for line in proc.stdout.splitlines():
            if line.startswith("{"):
                d = json.loads(line)
                results.append(TTSResult(Path(d["out"]), d["sec_audio"], d["sec_compute"], d.get("device", "")))
        if len(results) != len(jobs):
            raise RuntimeError(f"parler worker returned {len(results)} results for {len(jobs)} jobs")
        return results


class MlxAudioBackend(TTSBackend):
    """Any mlx-audio TTS model (Maya2 Native, Chatterbox Multilingual, ...), run in the isolated
    tts-mlx/ env as a subprocess. voice_cfg keys: model, speaker (built-in voice name, optional),
    lang (default hi), ref_audio (repo-relative synthetic reference clip, optional), ref_text,
    params (generate() options for this voice), worker (script in tts-mlx/, default mlx_worker.py;
    snac_lm_worker.py + flavor for Indic-Speak / Veena, which mlx-audio doesn't cover)."""

    name = "mlx_audio"
    PROJECT = REPO_ROOT / "tts-mlx"

    def synthesize_many(self, jobs, voice_cfg):
        ref = voice_cfg.get("ref_audio")
        if ref:
            ref = str((REPO_ROOT / ref).resolve())
            if not Path(ref).exists():
                raise SystemExit(f"reference clip not found: {ref}")
        base = dict(voice_cfg.get("params") or {})
        req = {"model": voice_cfg["model"], "lang": voice_cfg.get("lang", "hi"),
               "flavor": voice_cfg.get("flavor", ""), "jobs": []}
        for j in jobs:
            j.out.parent.mkdir(parents=True, exist_ok=True)
            job = {"text": j.text, "out": str(j.out), "seed": int(j.seed if j.seed is not None else voice_cfg.get("seed", 42)),
                   "params": {**base, **(j.params or {})}}
            if voice_cfg.get("speaker") and not ref:
                job["voice"] = voice_cfg["speaker"]
            if ref:
                job["ref_audio"], job["ref_text"] = ref, voice_cfg.get("ref_text", "")
            req["jobs"].append(job)
        worker = self.PROJECT / voice_cfg.get("worker", "mlx_worker.py")  # e.g. indic_speak_worker.py
        cmd = ["uv", "run", "--project", str(self.PROJECT), "python", str(worker)]
        log.info("mlx_audio: %d job(s), model=%s, voice=%s", len(jobs), voice_cfg["model"], voice_cfg.get("speaker") or ref)
        proc = subprocess.run(cmd, input=json.dumps(req, ensure_ascii=False), stdout=subprocess.PIPE,
                              stderr=None, text=True, env={**os.environ, "TOKENIZERS_PARALLELISM": "false"})
        if proc.returncode != 0:
            raise RuntimeError(f"mlx worker failed (exit {proc.returncode}); see messages above")
        results = [TTSResult(Path(d["out"]), d["sec_audio"], d["sec_compute"], d.get("device", ""))
                   for d in (json.loads(x) for x in proc.stdout.splitlines() if x.startswith("{"))]
        if len(results) != len(jobs):
            raise RuntimeError(f"mlx worker returned {len(results)} results for {len(jobs)} jobs")
        return results


class StubBackend(TTSBackend):
    """No model: a quiet tone whose length follows the word count (~140 wpm).
    For testing the pipeline and rendering before real narration exists."""

    name = "stub"

    def synthesize_many(self, jobs, voice_cfg):
        out = []
        for j in jobs:
            j.out.parent.mkdir(parents=True, exist_ok=True)
            sec = max(1.0, len(j.text.split()) / (140 / 60)) * (1 + 0.02 * ((j.seed or 0) % 5))
            run_cmd(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                     f"sine=frequency=220:duration={sec:.2f}:sample_rate=44100", "-af", "volume=0.2", str(j.out)])
            out.append(TTSResult(j.out, wav_duration(j.out), 0.0, "stub"))
        return out


BACKENDS: dict[str, type[TTSBackend]] = {"parler": ParlerBackend, "mlx_audio": MlxAudioBackend, "stub": StubBackend}


def get_backend(name: str) -> TTSBackend:
    try:
        return BACKENDS[name]()
    except KeyError:
        raise SystemExit(f"unknown tts backend {name!r}; available: {', '.join(BACKENDS)}")
