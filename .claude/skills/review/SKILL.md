---
name: review
description: Quality-check a rendered AgriGate episode by inspecting contact sheets and automated loudness/duration/black-frame checks, and complete review/review.md. Use after the final render.
---

# review

```bash
uv run python -m pipeline.review episodes/<id> [--draft]
```

This writes `review/sheet-NN.png`: a frame every 2 s, 12 per sheet, with the time in the bottom-left corner. It also writes `review/checks.json` and `review/review.md`, which contains the automated results (duration, loudness, black frames, static stretches), the scene start times and a manual checklist marked TODO.

**Open every sheet.** Then replace each TODO in `review.md` with PASS or FAIL and the timestamps:
- Devanagari: no broken conjuncts, no dotted circles (◌)
- Captions: readable, at most 2 lines, inside the margins. Shorts: above the bottom ~25%, clear of the right-side buttons.
- Text never covers the key part of an image
- Visuals match the narration (use the scene start times to map timestamps to scenes)
- No black or frozen frames. A static stretch on a graphic hold is fine; on an image or B-roll scene it is not.
- Watermark present throughout
- Indian rural context; no garbled text inside images
- **People in every frame** (the same checklist as `config.yaml: images.inspection_checklist`): 2 arms, 2 hands, 5 fingers on each visible hand, 2 legs, natural posture, correct dress, tools held correctly. For any frame with people, extract it at full size (`ffmpeg -ss <t> -i render/video.mp4 -frames:v 1 x.png`) and check it person by person. A contact-sheet thumbnail is too small to count fingers.

Write the verdict. Fix any FAIL by rerunning only the affected scene and stage, then render and review again. Finish with `validate --set-status reviewed`; it fails while any TODO remains.
