# Log — 2026-11-19-ramesh-mitti-jaanch-pilot

## new_episode — 2026-11-19 22:47:34
- duration: 0.0s
- outcome: ok
- created: brief.md, episode.json, log.md

## text_normalize — 2026-11-19 22:47:52
- duration: 0.0s
- outcome: ok
- narration_spoken built for 8 scene(s)

## validate — 2026-11-19 22:47:52
- duration: 0.0s
- outcome: ok
- PASS as current status: 0 errors, 2 warnings

## validate — 2026-11-19 22:48:12
- duration: 0.0s
- outcome: ok
- PASS as current status: 0 errors, 1 warnings

**CHECKPOINT 1 — script approved by the user on 2026-11-19. Cast: user picked ramesh candidate 3, sunita candidate 3.**

## validate — 2026-11-19 22:58:22
- duration: 0.0s
- outcome: ok
- PASS as script_approved: 0 errors, 1 warnings
- status draft → script_approved

## narration — 2026-11-19 22:58:24
- duration: 301.6s
- outcome: ok
- mode=segments backend=mlx_audio speaker=Vasant seed=42
- synthesizing 88 take(s) (4 per segment)
- TTS: 279.2s audio in 244s compute (0.9× realtime)
- scoring 88 take(s) (asr: whisper)
- voice pitch 145 Hz; per style: neutral 145 Hz, slow 144 Hz, warm 147 Hz
- loudness -27.9 → -14.4 LUFS (target -14.0), true peak -1.9 dBTP, gain +13.9 dB, limiter on, room tone -66 dB
- 8 scenes, narration total 74.9s

## validate — 2026-11-19 23:03:52
- duration: 0.0s
- outcome: ok
- PASS as narrated: 0 errors, 1 warnings
- status script_approved → narrated

## images — 2026-11-19 23:03:52
- duration: 938.8s
- outcome: ok
- scene 1 shot 1: attempt 1, seed 187127, cast ramesh, 39.6s → scene-01-s1-a1.png
- scene 1 shot 2: attempt 1, seed 47650, cast ramesh, 44.9s → scene-01-s2-a1.png
- scene 2 shot 1: attempt 1, seed 188509, 23.7s → scene-02-s1-a1.png
- scene 2 shot 2: attempt 1, seed 714175, 24.3s → scene-02-s2-a1.png
- scene 3 shot 1: attempt 1, seed 477554, cast ramesh, 54.0s → scene-03-s1-a1.png
- scene 4 shot 1: attempt 1, seed 150902, cast ramesh, 52.7s → scene-04-s1-a1.png
- scene 4 shot 2: attempt 1, seed 496312, cast ramesh, 53.7s → scene-04-s2-a1.png
- scene 5 shot 1: attempt 1, seed 668620, cast ramesh, 75.8s → scene-05-s1-a1.png
- scene 5 shot 2: attempt 1, seed 115030, cast ramesh, 80.5s → scene-05-s2-a1.png
- scene 6 shot 1: attempt 1, seed 612987, cast ramesh+sunita, 136.1s → scene-06-s1-a1.png
- scene 6 shot 2: attempt 1, seed 207363, cast sunita, 78.3s → scene-06-s2-a1.png
- scene 7 shot 1: attempt 1, seed 600560, cast ramesh, 79.4s → scene-07-s1-a1.png
- scene 7 shot 2: attempt 1, seed 721876, 34.9s → scene-07-s2-a1.png
- scene 7 shot 3: attempt 1, seed 122000, cast ramesh, 81.9s → scene-07-s3-a1.png
- scene 8 shot 1: attempt 1, seed 577459, cast ramesh, 78.6s → scene-08-s1-a1.png

## image inspection — 2026-11-20 08:52:22
- duration: 0.0s
- outcome: ok
- scene 3 shot 1: inspection FAIL (scene-03-s1.png) — two buckets; khurpi fused through the second bucket handle; standing wheat while narration says the field was empty

## image inspection — 2026-11-20 08:52:22
- duration: 0.0s
- outcome: ok
- scene 4 shot 1: inspection FAIL (scene-04-s1.png) — standing wheat; narration: sampling after harvest, field empty

## image inspection — 2026-11-20 08:52:22
- duration: 0.0s
- outcome: ok
- scene 7 shot 2: inspection FAIL (scene-07-s2.png) — three hands: a third hand enters from the bottom (two people + extra)

## images — 2026-11-20 08:52:22
- duration: 37.8s
- outcome: ok
- scene 3 shot 1: attempt 2, seed 192467, cast ramesh, 37.8s → scene-03-s1-a2.png

## images — 2026-11-20 08:53:00
- duration: 37.5s
- outcome: ok
- scene 4 shot 1: attempt 2, seed 919943, cast ramesh, 37.5s → scene-04-s1-a2.png

## images — 2026-11-20 08:53:38
- duration: 18.3s
- outcome: ok
- scene 7 shot 2: attempt 2, seed 84367, 18.3s → scene-07-s2-a2.png

## image inspection — 2026-11-20 08:54:22
- duration: 0.0s
- outcome: ok
- scene 1 shot 1: inspection PASS (scene-01-s1.png) — ramesh: 2 arms/2 hands (right on sack, left free, 5 fingers in crop), 2 legs, walking OK; sack single, label illegible; identity: face/receding grey hair/grey beard+moustache, white kurta-pyjama, pale green gamchha left shoulder, chappals match ref

## image inspection — 2026-11-20 08:54:22
- duration: 0.0s
- outcome: ok
- scene 1 shot 2: inspection PASS (scene-01-s2.png) — ramesh: right hand at chin, left on hip, 2 legs, standing OK; young crop rows; identity: face/hair/beard/kurta/gamchha match ref, nothing added

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 2 shot 1: inspection PASS (scene-02-s1.png) — no people; two fields dark vs pale soil split by a bund; village houses, palms in background (slightly coastal look, acceptable); no text

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 2 shot 2: inspection PASS (scene-02-s2.png) — no people; fertilizer sacks, labels illegible print (realistic); bucket single handle

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 3 shot 1: inspection PASS (scene-03-s1.png) — attempt 2. ramesh: 2 arms/2 hands each holding a bucket by its handle, 2 legs walking; harvested stubble field now; carries two buckets (khurpi rests inside the left one, not fused); identity: face/hair/beard, kurta-pyjama, gamchha match ref

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 4 shot 1: inspection PASS (scene-04-s1.png) — attempt 2. ramesh small in frame: 2 arms, bucket in left hand, 2 legs; harvested stubble, line of dug pits; identity: grey hair/beard, white kurta, green gamchha match ref at small size

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 4 shot 2: inspection PASS (scene-04-s2.png) — ramesh squatting: 2 arms/2 hands (right on khurpi single handle in pit, left on bucket rim), 2 legs, chappals; identity: pair checked, face/hairline/beard/kurta/gamchha match ref

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 5 shot 1: inspection PASS (scene-05-s1.png) — ramesh squatting: right hand holds khurpi (single handle) with soil slice, left hand on bucket rim, 5 fingers (crop), 2 legs; bucket sits in pit (odd but plausible); identity: face/hair/beard/kurta/gamchha match ref

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 5 shot 2: inspection PASS (scene-05-s2.png) — ramesh cross-legged under tree: 2 hands tying cloth bag, 2 feet in chappals; soil on blue sheet; identity: face/hair/beard/kurta/gamchha match ref

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 6 shot 1: inspection PASS (scene-06-s1.png) — ramesh: 2 hands on bag; sunita: right hand touches bag top, left flat on counter with bangle; every hand traced to own arm in zoomed crop, no fusion; counter between them; wall chart illegible; identity: ramesh matches ref; sunita bun/bindi/cream dupatta/blue kameez/white coat/bangle match ref (pair checked)

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 6 shot 2: inspection PASS (scene-06-s2.png) — sunita seated: 2 hands holding cloth bag over white dish, 5 fingers, bangle; charts illegible; identity: pair checked, bun/bindi/dupatta/kameez/coat match, face slightly fuller but same person

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 7 shot 1: inspection PASS (scene-07-s1.png) — ramesh on wooden bench: 2 hands holding report sheet, 2 legs; report text illegible; identity: face/hair/beard/kurta/gamchha match ref

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 7 shot 2: inspection PASS (scene-07-s2.png) — attempt 2. hands only: exactly 2 hands from white kurta sleeves (one person), thumbs + fingers natural; report header garbled/illegible, bar chart

## image inspection — 2026-11-20 08:54:23
- duration: 0.0s
- outcome: ok
- scene 7 shot 3: inspection PASS (scene-07-s3.png) — ramesh standing: 2 arms/2 hands at sides, 2 legs, chappals; young green crop rows; identity: face/hair/beard/kurta/gamchha match ref

## image inspection — 2026-11-20 08:54:24
- duration: 0.0s
- outcome: ok
- scene 8 shot 1: inspection PASS (scene-08-s1.png) — ramesh: hands joined in namaste (2 hands, fingers aligned), 2 legs, chappals; smiling; identity: face/hair/beard/kurta/gamchha match ref

## validate — 2026-11-20 08:54:24
- duration: 0.0s
- outcome: ok
- PASS as visuals_ready: 0 errors, 1 warnings
- status narrated → visuals_ready

## render (draft) — 2026-11-20 08:54:28
- duration: 36.2s
- outcome: ok
- rendering draft.mp4: 1920x1080 × 0.5, expected 82.20s
- episodes/2026-11-19-ramesh-mitti-jaanch-pilot/render/draft.mp4: 82.22s (39.9 MB)

## validate — 2026-11-20 08:55:08
- duration: 0.0s
- outcome: ok
- PASS as draft_rendered: 0 errors, 1 warnings
- status visuals_ready → draft_rendered

## review — 2026-11-20 08:55:08
- duration: 4.4s
- outcome: ok
- 4 sheet(s) from 42 frames; duration PASS, loudness -14.5 LUFS, black segments 0

## checkpoint 2 — 2026-11-20
- REJECTED by the user: the story format compressed the informative content. The cast is for consistent faces only (ARCHITECTURE D28). Replaced by episodes/2026-11-20-mitti-ki-jaanch-v3. Kept as a record; do not publish.
