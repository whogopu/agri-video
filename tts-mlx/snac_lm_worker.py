"""Worker for Llama-style TTS models that emit SNAC audio tokens (7 per frame), run with mlx-lm.
Runs inside the isolated tts-mlx/ env. Same JSON contract as mlx_worker.py.

    uv run --project tts-mlx python tts-mlx/snac_lm_worker.py < request.json

Request: {"model": "...", "flavor": "indic_speak" | "veena",
          "jobs": [{"text", "out", "seed", "voice", "params": {"style", "temperature", ...}}]}

Flavors:
- indic_speak: Bodhan AI Indic-Speak (community MLX bf16 conversion iniquitous/indic-speak-mlx-bf16).
  Prompt with <|speaker>/<|style> blocks, SNAC codes decoded by its fine-tuned Vocos (vocos_decoder.py).
  License: Indic Open Model License v1.0 + Llama 3.2 Community License.
- veena: Maya Research Veena (maya-research/Veena, Apache-2.0), prompt "<spk_name> text", plain SNAC decode.

Written here instead of running repo code (tts_mlx.py, inference.py), and the Vocos checkpoint is
loaded with weights_only=True, so nothing from a downloaded repo can execute. Prompt formats and code
layouts follow each model's card / reference inference code.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_logits_processors, make_sampler

SR = 24_000
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # our own vocos_decoder.py


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def build_prompt(tok, text: str, speaker: str = "", style: str = "") -> list[int]:
    """<|start_of_human|><|begin_of_text|>[<|speaker>..<speaker|>\\n][<|style>..<style|>\\n]text<|eot_id|>
    <|end_of_human|><|start_of_ai|><|start_of_speech|>"""
    tid = tok.convert_tokens_to_ids
    enc = lambda s: tok.encode(s, add_special_tokens=False)  # noqa: E731
    nl = enc("\n")
    blocks = []
    if speaker.strip():
        blocks.append([tid("<|speaker>")] + enc(speaker.strip()) + [tid("<speaker|>")])
    if style.strip():
        blocks.append([tid("<|style>")] + enc(style.strip()) + [tid("<style|>")])
    meta: list[int] = []
    for i, b in enumerate(blocks):
        meta += (nl if i else []) + b
    if blocks:
        meta += nl
    body = [tok.bos_token_id] + meta + enc(text) + [tid("<|eot_id|>")]
    return ([tid("<|start_of_human|>")] + body + [tid("<|end_of_human|>")]
            + [tid("<|start_of_ai|>"), tid("<|start_of_speech|>")])


VEENA = {"soh": 128259, "eoh": 128260, "soa": 128261, "sos": 128257, "eos": 128258, "eoa": 128262, "base": 128266}


def build_prompt_veena(tok, text: str, speaker: str) -> list[int]:
    """[HUMAN] <spk_name> text [/HUMAN] [AI] [SPEECH] (maya-research/Veena model card)."""
    body = tok.encode(f"<spk_{speaker}> {text}", add_special_tokens=False)
    return [VEENA["soh"], *body, VEENA["eoh"], VEENA["soa"], VEENA["sos"]]


def ids_to_codes(ids: list[int], base: int, device: str) -> list[torch.Tensor]:
    """7 tokens per SNAC frame: [c0, c1a, c2a, c2b, c1b, c2c, c2d], each offset by k*4096."""
    n = len(ids) // 7
    a = np.asarray(ids[: n * 7], dtype=np.int64).reshape(n, 7) - base
    a = a - (np.arange(7) * 4096)[None, :]
    a = a[np.all((a >= 0) & (a < 4096), axis=1)]  # drop frames with an out-of-range code (as upstream)
    if a.shape[0] == 0:
        raise ValueError("model emitted no valid SNAC frame")
    c0 = a[:, 0]
    c1 = np.stack([a[:, 1], a[:, 4]], 1).reshape(-1)
    c2 = np.stack([a[:, 2], a[:, 3], a[:, 5], a[:, 6]], 1).reshape(-1)
    return [torch.from_numpy(c).unsqueeze(0).to(device) for c in (c0, c1, c2)]


def main() -> None:
    req = json.load(sys.stdin)
    t0 = time.monotonic()
    path = Path(snapshot_download(req.get("model", "iniquitous/indic-speak-mlx-bf16")))
    model, tok = load(str(path))
    from snac import SNAC
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").to(dev).eval()
    flavor = req.get("flavor", "indic_speak")
    if flavor == "veena":
        vocos = None
        base = VEENA["base"]
        eos = {VEENA["eos"], VEENA["eoa"], tok.eos_token_id}
    else:
        from vocos_decoder import load_vocos
        vocos = load_vocos(path / "vocos", dev)
        base = tok.convert_tokens_to_ids("<|snac_0|>")
        eos = {tok.convert_tokens_to_ids("<|end_of_speech|>"), tok.eos_token_id}
    hi = base + 7 * 4096
    log(f"{req.get('model')} ({flavor}) loaded on {dev} in {time.monotonic() - t0:.1f}s")

    for i, job in enumerate(req["jobs"], 1):
        t0 = time.monotonic()
        p = job.get("params") or {}
        mx.random.seed(int(job.get("seed", 42)))
        text = job["text"]
        cap = min(int((2 * len(text) / 12 + 3) * 98), 2520)  # ~98 tokens per audio second, 2× margin
        veena = flavor == "veena"
        sampler = make_sampler(temp=float(p.get("temperature", 0.4 if veena else 0.6)),
                               top_p=float(p.get("top_p", 0.9)), top_k=int(p.get("top_k", 0 if veena else 50)))
        procs = make_logits_processors(repetition_penalty=float(p.get("repetition_penalty", 1.05 if veena else 1.2)))
        if veena:
            prompt = build_prompt_veena(tok, text, (job.get("voice") or "agastya").lower())
        else:
            prompt = build_prompt(tok, text, job.get("voice") or "Amit", p.get("style", ""))
        ids = []
        for r in stream_generate(model, tok, prompt, max_tokens=cap, sampler=sampler, logits_processors=procs):
            if r.token in eos or not (base <= r.token < hi):
                break
            ids.append(r.token)
        with torch.no_grad():
            codes = ids_to_codes(ids, base, dev)
            if vocos is None:
                wav = snac.decode(codes)[0, 0].clamp(-1, 1).float().cpu().numpy()
            else:
                z = snac.quantizer.from_codes(codes)
                wav = vocos(z.float())[0, 0].clamp(-1, 1).float().cpu().numpy()
        sf.write(job["out"], wav, SR)
        out = {"out": job["out"], "sec_audio": round(len(wav) / SR, 3), "sec_compute": round(time.monotonic() - t0, 2),
               "device": f"mlx+{dev}", "sample_rate": SR, "hit_cap": len(ids) >= cap}
        log(f"[{i}/{len(req['jobs'])}] {out['sec_audio']}s audio in {out['sec_compute']}s")
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
