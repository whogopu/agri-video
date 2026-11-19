---
name: index-broll
description: Add new B-roll clips from assets/broll/clips/ to assets/broll/index.json with descriptions, tags, quality notes and license. Use when the user adds clips to the library.
---

# index-broll

Optional. Most episodes use generated images and graphics only. Run this only when the user adds clips.

```bash
uv run python -m pipeline.broll index    # probe new clips, write stub entries + frames/<id>.jpg (start | middle | end)
uv run python -m pipeline.broll check    # what's still missing
uv run python -m pipeline.broll list [--tag wheat] [--orientation portrait]
```

For each new clip:
1. **Look at `assets/broll/frames/<id>.jpg`.** If the clip changes a lot between frames, extract more frames with ffmpeg and look at those too.
2. Fill in its entry in `assets/broll/index.json`:
   - `description_en`, `description_hi`: what is visible, 1–2 sentences. Plain Hindi.
   - `tags`: `crop` (wheat, paddy, mustard…), `activity` (sowing, spraying, harvesting, soil-sampling…), `setting` (field, mandi, village, KVK…), `season` (rabi, kharif, or the visible crop stage), `shot_type` (wide, close-up, aerial, handheld, static, pan).
   - `usable_segments`: in/out seconds of steady, clean stretches, each with a short note.
   - `quality_notes`: shaky, low light, burned-in text or watermark, logos, anything non-Indian.
   - `people_visible`: `true` if anyone is identifiable. Such clips need written consent before use, and validate warns about them.
3. Fill in `source`, `license` and `source_url`. **Ask the user if you don't know them.** Never guess a license. A clip without one stays unusable: `check` fails and `validate` rejects it.
4. Run `check` until the new clips pass.
