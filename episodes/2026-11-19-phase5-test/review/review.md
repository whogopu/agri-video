# Review — 2026-11-19-phase5-test

Video: `render/video.mp4` · 1920x1080 · long

## Automated checks

| Check | Result | Details |
|---|---|---|
| Duration | PASS | 30.61s (expected 30.60s from scenes) |
| Loudness | PASS | -14.5 LUFS (target -14), true peak -4.9 dBTP (ceiling -1.5) |
| Black frames | PASS | none |
| Static stretches ≥4 s | info | none — fine on graphic holds, a problem on image/B-roll scenes |

## Scene starts

1: 0:00.0 (image) · 2: 0:07.4 (graphic) · 3: 0:15.7 (image) · 4: 0:23.5 (graphic)

## Contact sheets

- `review/sheet-01.png`
- `review/sheet-02.png`

## Manual checks (Claude: look at every sheet, then fill in)

| Check | Result | Timestamps / notes |
|---|---|---|
| Devanagari renders correctly (no broken conjuncts, no dotted circles ◌) | PASS | conjuncts in ज़रूरी, क्षेत्र-type clusters, सेंटीमीटर all clean |
| Captions readable, max 2 lines, inside safe margins | PASS | all single-line chunks, bottom-centred inside margins |
| Text never covers the key part of an image | PASS | tag top-left over sky/field; captions below the hands and the pit |
| Visuals match the narration | PASS | hook = soil in hands; explain = key points; step = digging sample pit; CTA = title card |
| No black or frozen frames (beyond intentional graphic holds) | PASS | automated: none; Ken Burns motion visible on image scenes |
| Watermark present throughout | PASS | top-right on every frame |
| Indian rural context everywhere; no garbled text inside images | PASS | wheat field, mud-brick houses, rice stubble; no text in images |

## Verdict

PASS. Pipeline test episode (not real content); ready for packaging.
