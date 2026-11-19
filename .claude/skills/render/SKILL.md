---
name: render
description: Render an AgriGate episode with Remotion — 540p draft for checkpoint 2, then 1080p final. Use after visuals are ready or after applying draft notes.
---

# render

```bash
uv run python -m pipeline.render episodes/<id> --draft                 # 540p → render/draft.mp4 (needs visuals_ready)
uv run python -m pipeline.validate episodes/<id> --set-status draft_rendered
# CHECKPOINT 2 — wait for the user's notes
uv run python -m pipeline.render episodes/<id>                         # 1080p → render/video.mp4 (needs draft_rendered)
uv run python -m pipeline.validate episodes/<id> --set-status final_rendered
```

- `render.py` validates first. It hard-links the episode's audio and images (and any B-roll and the logo) into `remotion/public/`, writes `render/props.json`, and runs Remotion with H.264/AAC and VideoToolbox. Format comes from `episode.json`: long is 1920×1080, short is 1080×1920.
- Speed on this Mac: roughly 0.45 s of render time per second of video, for both draft and final.
- It skips the render if the output is newer than `episode.json`. Pass `--force` to re-render anyway.
- **CHECKPOINT 2:** give the user the path to `render/draft.mp4` and wait. Apply notes scene by scene, rerunning only the affected stage with `--scene N` (`--force` or `--retry` for images; `--force` for narration after a text change), then render the draft again or go to final as the user says.
