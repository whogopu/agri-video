# Review — 2026-11-19-mitti-ki-jaanch

Video: `render/video.mp4` · 1920x1080 · long

## Automated checks

| Check | Result | Details |
|---|---|---|
| Duration | PASS | 250.75s (expected 250.73s from scenes) |
| Loudness | PASS | -14.2 LUFS (target -14), true peak -4.8 dBTP (ceiling -1.5) |
| Black frames | PASS | none |
| Static stretches ≥4 s | info | none — fine on graphic holds, a problem on image/B-roll scenes |

## Scene starts

1: 0:00.0 (image) · 2: 0:11.3 (graphic) · 3: 0:19.4 (image) · 4: 0:33.1 (image) · 5: 0:44.4 (image) · 6: 0:56.7 (graphic) · 7: 1:12.3 (image) · 8: 1:24.4 (image) · 9: 1:34.6 (image) · 10: 1:44.7 (graphic) · 11: 1:54.8 (graphic) · 12: 2:03.6 (image) · 13: 2:08.8 (image) · 14: 2:22.2 (graphic) · 15: 2:31.2 (image) · 16: 2:47.5 (image) · 17: 2:57.2 (graphic) · 18: 3:11.3 (image) · 19: 3:20.2 (image) · 20: 3:30.0 (image) · 21: 3:41.5 (graphic) · 22: 3:52.2 (graphic) · 23: 4:02.2 (graphic)

## Contact sheets

- `review/sheet-01.png`
- `review/sheet-02.png`
- `review/sheet-03.png`
- `review/sheet-04.png`
- `review/sheet-05.png`
- `review/sheet-06.png`
- `review/sheet-07.png`
- `review/sheet-08.png`
- `review/sheet-09.png`
- `review/sheet-10.png`
- `review/sheet-11.png`

## Manual checks (Claude: look at every sheet, then fill in)

| Check | Result | Timestamps / notes |
|---|---|---|
| Devanagari renders correctly (no broken conjuncts, no dotted circles ◌) | PASS | all 11 sheets; no ◌ |
| Captions readable, max 2 lines, inside safe margins | PASS | single-line chunks, bottom-centred; no lone single-word caption |
| Text never covers the key part of an image | PASS | tags top-left; at 2:32–2:42 caption sits on the table below both people's hands |
| Visuals match the narration | PASS | scene 15 now shows the sample being handed in at the lab table (user's composition) |
| No black or frozen frames (beyond intentional graphic holds) | PASS | automated: none |
| Watermark present throughout | PASS | top-right on every sampled frame |
| Indian rural context everywhere; no garbled text inside images | PASS | only illegible incidental text (lab charts, report, notice board) — wanted per user |
| People: 2 arms/hands/legs each, 5 fingers per visible hand, natural posture, correct dress, tools held correctly (config images.inspection_checklist) | PASS | all 14 images inspected (incl. separate-people and both-hands-visible rules); scene 15 attempt 5 re-checked in final 1080p frames 2:32 and 2:42 |

## Verdict

PASS — final with scene 15 attempt 5. All user notes resolved; see log.md.
