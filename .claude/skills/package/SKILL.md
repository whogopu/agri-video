---
name: package
description: Make the thumbnail and YouTube metadata (youtube.md) for a reviewed AgriGate episode. Use as the last stage before checkpoint 3.
---

# package

1. Write the `package` section of `episode.json`:
   - `youtube_title`: Hindi, under 70 characters, clear benefit to the farmer, no clickbait. For Shorts, `#Shorts` is added automatically.
   - `description_hi`: 2–3 short Hindi sentences summarizing the video. Sources and the disclaimer (`config.yaml: package.disclaimer_hi`) are appended automatically.
   - `tags`: about 10, mixing Hindi and the English terms farmers search for.
   - `thumbnail_text`: 3–5 big Hindi words.
   - `thumbnail_image`: the strongest image, e.g. `images/scene-03.png`. Default: the first image scene.
   - `sources_list`: readable source names (title, publisher, year), not file names.
   - `synthetic_content`: leave unset. It is set to true automatically when the video has generated images (YouTube's "altered or synthetic content" disclosure).
2. Run:
   ```bash
   uv run python -m pipeline.package episodes/<id>      # → render/thumbnail.png (1280×720, or 1080×1920 for Shorts) + youtube.md
   uv run python -m pipeline.validate episodes/<id> --set-status packaged
   ```
3. **Look at the thumbnail:** the title is readable at small size, it doesn't cover the subject's face, and the logo is visible.
4. **CHECKPOINT 3:** give the user the paths to `render/video.mp4`, `render/thumbnail.png` and `youtube.md`. The user uploads manually; `youtube.md` has the upload checklist.
