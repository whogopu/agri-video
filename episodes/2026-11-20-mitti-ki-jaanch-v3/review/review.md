# Review — 2026-11-20-mitti-ki-jaanch-v3

Video: `render/draft.mp4` · 1920x1080 · long

## Automated checks

| Check | Result | Details |
|---|---|---|
| Duration | PASS | 238.93s (expected 238.93s from scenes) |
| Loudness | PASS | -14.3 LUFS (target -14), true peak -4.7 dBTP (ceiling -1.5) |
| Black frames | PASS | none |
| Static stretches ≥4 s | info | none — fine on graphic holds, a problem on image/B-roll scenes |

## Scene starts

1: 0:00.0 (image) · 2: 0:09.4 (graphic) · 3: 0:18.1 (image) · 4: 0:30.7 (image) · 5: 0:40.0 (image) · 6: 0:51.1 (graphic) · 7: 1:08.3 (image) · 8: 1:19.1 (image) · 9: 1:29.5 (image) · 10: 1:39.1 (graphic) · 11: 1:48.9 (graphic) · 12: 1:57.3 (image) · 13: 2:03.2 (image) · 14: 2:15.0 (graphic) · 15: 2:24.4 (image) · 16: 2:38.9 (image) · 17: 2:48.7 (graphic) · 18: 3:02.4 (image) · 19: 3:12.2 (image) · 20: 3:21.2 (image) · 21: 3:31.4 (graphic) · 22: 3:41.1 (graphic) · 23: 3:50.8 (graphic)

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

## Manual checks (Claude: look at every sheet, then fill in)

| Check | Result | Timestamps / notes |
|---|---|---|
| Devanagari renders correctly (no broken conjuncts, no dotted circles ◌) | PASS | all 10 sheets; word spans split only at spaces, conjuncts intact (प्रयोगशाला, सूक्ष्म, ज़िंक) |
| Captions readable, max 2 lines, inside safe margins | PASS | one line throughout; green spoken-word highlight readable on photos and graphics (phase B2) |
| Text never covers the key part of an image | PASS | same layout as the approved phase-A draft |
| Visuals match the narration | PASS | key points and big numbers now appear on their spoken word (phase B3): 0:56 नाइट्रोजन, 1:00 ज़िंक, 1:06 pH, 1:46 15 सेमी, 1:54 2.5–3 सेमी, 2:54–3:00 the five places, 3:38 3 साल, 3:44–3:50 recap. NOTE: before its number, a BigNumber shows only its label: 1:39–1:45 "गड्ढे की गहराई", 1:49–1:53 "मोटी परत काटें", 3:31–3:37 "का एक चक्र" (a fragment that reads oddly alone). Design question for the user |
| No black or frozen frames (beyond intentional graphic holds) | PASS | automated check: none |
| Watermark present throughout | PASS | top-right on every frame |
| Indian rural context everywhere; no garbled text inside images | TODO | |
| People: 2 arms/hands/legs each, 5 fingers per visible hand, natural posture, correct dress, tools held correctly (config images.inspection_checklist) | TODO | |

## Verdict

TODO
