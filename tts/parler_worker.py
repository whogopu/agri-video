"""Indic Parler-TTS worker. Runs inside the isolated tts/ env (transformers is pinned there).

    uv run --project tts python tts/parler_worker.py < request.json

Request (stdin, JSON):
    {"model": "ai4bharat/indic-parler-tts", "device": "mps", "seed": 42,
     "jobs": [{"text": "...", "description": "...", "out": "/abs/path.wav"}]}

The model loads once per request. For each job, writes a mono WAV at the model's
native sample rate and prints one JSON line to stdout:
    {"out": ..., "sec_audio": 4.2, "sec_compute": 9.8, "device": "mps"}
Progress and warnings go to stderr. Post-processing (resample, trim, loudness) is
done by pipeline/narration.py, not here.
"""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # CPU fallback for ops MPS lacks

import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from parler_tts import ParlerTTSForConditionalGeneration  # noqa: E402
from transformers import AutoTokenizer, set_seed  # noqa: E402


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def pick_device(want: str) -> str:
    if want == "mps" and torch.backends.mps.is_available():
        return "mps"
    if want == "mps":
        log("MPS not available, falling back to CPU")
    return "cpu"


def load(model_id: str, device: str):
    t0 = time.monotonic()
    model = ParlerTTSForConditionalGeneration.from_pretrained(model_id).to(device)
    model.eval()
    tok = AutoTokenizer.from_pretrained(model_id)
    desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    log(f"model loaded on {device} in {time.monotonic() - t0:.1f}s")
    return model, tok, desc_tok


@torch.inference_mode()
def generate(model, tok, desc_tok, device: str, text: str, description: str, seed: int):
    set_seed(seed)  # same seed + text + description → same voice/prosody
    d = desc_tok(description, return_tensors="pt").to(device)
    p = tok(text, return_tensors="pt").to(device)
    out = model.generate(
        input_ids=d.input_ids,
        attention_mask=d.attention_mask,
        prompt_input_ids=p.input_ids,
        prompt_attention_mask=p.attention_mask,
    )
    return out.to(torch.float32).cpu().numpy().squeeze()


def main() -> None:
    req = json.load(sys.stdin)
    device = pick_device(req.get("device", "mps"))
    model, tok, desc_tok = load(req["model"], device)
    sr = model.config.sampling_rate
    for i, job in enumerate(req["jobs"], 1):
        t0 = time.monotonic()
        try:
            audio = generate(model, tok, desc_tok, device, job["text"], job["description"], req.get("seed", 42))
        except RuntimeError as e:
            if device != "mps":
                raise
            log(f"MPS failed ({e}); retrying job {i} on CPU")
            device = "cpu"
            model = model.to("cpu")
            audio = generate(model, tok, desc_tok, device, job["text"], job["description"], req.get("seed", 42))
        sf.write(job["out"], audio, sr)
        res = {"out": job["out"], "sec_audio": round(len(audio) / sr, 3),
               "sec_compute": round(time.monotonic() - t0, 2), "device": device, "sample_rate": sr}
        log(f"[{i}/{len(req['jobs'])}] {res['sec_audio']}s audio in {res['sec_compute']}s")
        print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
