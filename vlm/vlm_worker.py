"""Local vision-language worker. Runs in the isolated vlm/ env (mlx-vlm, MIT).

    uv run --project vlm python vlm/vlm_worker.py < request.json

Request (stdin, JSON):
    {"model": "mlx-community/Qwen3.5-9B-8bit", "max_tokens": 1200, "temperature": 0.0,
     "enable_thinking": false, "max_pixels": 1600000,
     "jobs": [{"id": "s01-k1-full", "prompt": "...", "images": ["/abs/a.png", ...]}]}

For each job prints one JSON line to stdout as soon as it is done:
    {"id": ..., "text": "<model answer>", "sec": 12.3, "prompt_tokens": 2100, "gen_tokens": 180,
     "peak_mem_gb": 8.1}
or {"id": ..., "error": "..."}. The model is loaded once per request; progress goes to stderr.
Judging (what counts as a defect) happens in pipeline/vlm_inspect.py, so prompts and rules can change
without touching this env.
"""

from __future__ import annotations

import json
import sys
import time

from mlx_vlm import apply_chat_template, generate, load


def main() -> None:
    req = json.load(sys.stdin)
    t0 = time.time()
    model, processor = load(req["model"])
    print(f"vlm: loaded {req['model']} in {time.time() - t0:.1f}s", file=sys.stderr, flush=True)
    gen_kw = {"max_tokens": int(req.get("max_tokens", 1200)), "temperature": float(req.get("temperature", 0.0))}
    if req.get("max_pixels"):
        gen_kw["max_pixels"] = int(req["max_pixels"])
    tmpl_kw = {}
    if req.get("enable_thinking") is not None:
        tmpl_kw["enable_thinking"] = bool(req["enable_thinking"])
    for i, job in enumerate(req["jobs"], start=1):
        t = time.time()
        try:
            images = job.get("images") or []
            prompt = apply_chat_template(processor, model.config, job["prompt"], num_images=len(images), **tmpl_kw)
            r = generate(model, processor, prompt, image=images or None, verbose=False, **gen_kw)
            out = {"id": job["id"], "text": r.text, "sec": round(time.time() - t, 2),
                   "prompt_tokens": r.prompt_tokens, "gen_tokens": r.generation_tokens,
                   "peak_mem_gb": round(r.peak_memory, 2), "finish": r.finish_reason}
        except Exception as e:  # one bad job must not lose the rest
            out = {"id": job["id"], "error": f"{type(e).__name__}: {e}", "sec": round(time.time() - t, 2)}
        print(json.dumps(out, ensure_ascii=False), flush=True)
        print(f"vlm: {i}/{len(req['jobs'])} {job['id']} {out['sec']}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
