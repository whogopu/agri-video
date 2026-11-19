# AgriGate Hindi Video Pipeline — Project Brief (v0 build, v1 plan)

> **For Claude Code:** This file is your full brief. Your job in this session is to build **v0** as described below, phase by phase (section 10). Read the whole file first. At the end of each phase, run that phase's smoke test, summarize what works and what doesn't, and wait for my go-ahead before starting the next phase. **Ask me before downloading any model weights larger than 6 GB** (i have 16 gb unified ram, mac air m5) and before installing anything system-wide. Section 12 (v1) is for context only: do not build it, but don't make design choices that block it.

---

## 1. Context and goal

AgriGate works with farmers and the agriculture sector in India. We need regular **Hindi educational videos** for YouTube (one every 2–3 days), aimed at farmers.

The format is: **an AI narrator explains a topic in Hindi**, while the screen shows B-roll clips, generated still images with slow pan/zoom (Ken Burns), simple motion graphics (title cards, key points, numbers), and Hindi captions. Generated video clips are out of scope for v0.

This project is a **Claude Code workspace with skills**: I run each episode interactively in a Claude Code session, and Claude (you) orchestrates the stages, writes the script, chooses visuals, and reviews the output. The heavy media work runs **locally on my Mac** through Python scripts and Remotion.

Guiding principles:
- **Accuracy over automation.** Wrong farming advice (doses, dates, prices) can cost farmers real money. Facts come only from sources I provide.
- **Human checkpoints.** I approve the script, the draft render, and the final render.
- **Every stage is swappable.** Each stage is a script with a clear input/output contract and a backend set in `config.yaml`, so we can later move a stage to AWS or a paid API without touching the others.
- **Idempotent, per-scene stages.** Every stage skips outputs that already exist unless `--force` is given, and supports `--scene N` to redo one scene.

## 2. Audience and content rules

These rules also go into `CLAUDE.md` so they apply in every session.

- **Audience:** farmers in North India, mostly watching on phones. Many are not comfortable reading long text.
- **Language:** simple spoken Hindi (बोलचाल की हिंदी), not heavily Sanskritized. Use the English/Hinglish terms farmers actually use (यूरिया, DAP, स्प्रे, बीज दर) rather than formal translations nobody says.
- **Tone:** respectful, practical, like an experienced कृषि सलाहकार talking to a farmer. No hype, no fear-mongering.
- **Facts:** every dose, quantity, date, price, scheme detail, or product name must come from a file in the episode's `sources/` folder. If a claim isn't supported, write it as `[VERIFY: ...]` in the script. The pipeline must refuse to proceed past the script stage while any `[VERIFY` remains.
- **Chemicals and pesticides:** always add a short line telling viewers to read the product label and consult their local KVK or agriculture officer. Never recommend a specific brand unless I ask.
- **Images:** Indian rural context (Indian farmers, Indian crops and fields, Indian villages). No text inside generated images (models can't render Devanagari; all text is added in Remotion).
- **People:** never use a real person's face, name, or voice without their written consent. No voice cloning in v0.
- **Length:** 3–5 minutes per video. Hindi narration runs at roughly 130–150 words per minute, so target about 400–650 words.

## 3. Environment

- **Machine:** MacBook Air M5 (Apple Silicon, **fanless**). No CUDA. Run heavy jobs **one at a time**, never in parallel, and expect slowdowns on long jobs from thermal throttling. Unified memory size: **[I will tell you; ask me if I haven't]**. Choose model sizes and quantization to fit it.
- **Python:** use `uv` for environments and dependencies. Python 3.11 or 3.12. If the TTS library's dependency pins conflict with other packages, give TTS its own isolated environment and call it as a subprocess.
- **Node:** Node 20+ for Remotion.
- **System tools:** `ffmpeg` and `ffprobe` via Homebrew.
- **Image generation:** `mflux` (FLUX on Apple's MLX), installed as a uv tool. Check its current CLI flags with `--help` rather than assuming them.
- **Before relying on any tool or model:** run a small smoke test on this Mac and record the result and timing.
- **Licenses:** before adopting any model or library, check its license and note it in `docs/licenses.md`. This is a company project, so non-commercial licenses are not acceptable.

## 4. v0 architecture

```
brief.md + sources/            (I write these)
        │
        ▼
[1] script ──► script.md + episode.json          ◄── CHECKPOINT 1: I approve the script
        │
        ▼
[2] narration ──► audio/scene-XX.wav, durations, caption timings
        │
        ▼
[3] visuals ──► B-roll picks / generated images / graphic props per scene
        │
        ▼
[4] render (draft, 540p) ──► render/draft.mp4     ◄── CHECKPOINT 2: I review the draft
        │
        ▼
[4] render (final, 1080p) ──► render/video.mp4
        │
        ▼
[5] review ──► contact sheets + review.md (you inspect frames)
        │
        ▼
[6] package ──► thumbnail.png + youtube.md        ◄── CHECKPOINT 3: I approve and upload manually
```

`episode.json` is the **single source of truth** for an episode. Every stage reads it and writes its results back into it.

**Scene timing comes from narration.** Narration is generated **one audio file per scene**, so each scene's duration is the length of its audio plus a small pause. No audio alignment is needed for scene timing.

## 5. Repository structure

```
agri-video/
├── CLAUDE.md                     # project rules (from sections 1–3), commands, conventions
├── README.md                     # setup + how to make an episode, for humans
├── PROJECT_BRIEF.md              # this file
├── config.yaml                   # all tunable settings and backend choices
├── pronunciation.yaml            # word → spoken form fixes for TTS
├── pyproject.toml
├── .claude/
│   └── skills/
│       ├── make-episode/SKILL.md     # orchestrates the whole flow with checkpoints
│       ├── hindi-script/SKILL.md     # writing rules, structure, fact handling
│       ├── narration/SKILL.md
│       ├── visuals/SKILL.md          # B-roll choice, image prompts, regeneration rules
│       ├── render/SKILL.md
│       ├── review/SKILL.md           # frame-inspection checklist
│       ├── package/SKILL.md          # thumbnail + YouTube metadata
│       └── index-broll/SKILL.md      # describe new clips into the library index
├── pipeline/                     # Python package; one module per stage
│   ├── __init__.py
│   ├── common.py                 # load/save episode.json, config, logging, timing
│   ├── schema.py                 # episode.json schema + validation (pydantic)
│   ├── new_episode.py
│   ├── validate.py               # schema check, [VERIFY] check, length check
│   ├── narration.py              # TTS backends: parler (default), stub for others
│   ├── text_normalize.py         # Hindi numbers → words, units, pronunciation.yaml
│   ├── captions.py               # split text into caption chunks with timings
│   ├── images.py                 # image backends: mflux (default)
│   ├── broll.py                  # library index tools, trimming helpers
│   ├── render.py                 # sync assets into Remotion, call remotion render
│   ├── review.py                 # contact sheets, loudness/duration checks
│   └── package.py
├── remotion/                     # Remotion project (TypeScript)
│   ├── src/
│   │   ├── Root.tsx              # compositions: Episode, Thumbnail
│   │   ├── Episode.tsx           # reads props = episode.json
│   │   ├── scenes/
│   │   │   ├── KenBurnsImage.tsx
│   │   │   ├── BrollClip.tsx
│   │   │   ├── TitleCard.tsx
│   │   │   ├── KeyPoints.tsx
│   │   │   └── BigNumber.tsx
│   │   ├── overlays/
│   │   │   ├── Captions.tsx
│   │   │   ├── OnScreenText.tsx
│   │   │   └── Watermark.tsx
│   │   └── fonts.ts              # local Noto Sans Devanagari loading
│   └── public/
│       ├── fonts/                # Noto Sans Devanagari files (bundled locally)
│       └── episodes/             # render.py syncs the episode's assets here
├── assets/
│   ├── brand/                    # logo, colors (I'll provide)
│   ├── broll/
│   │   ├── clips/                # video files
│   │   └── index.json            # one entry per clip (see index-broll)
│   └── music/                    # (v1) royalty-free tracks
├── episodes/
│   └── YYYY-MM-DD-<slug>/
│       ├── brief.md              # topic, angle, target crop/region, notes
│       ├── sources/              # advisory PDFs, notes, links I provide
│       ├── script.md             # human-readable script for my review
│       ├── episode.json
│       ├── audio/
│       ├── images/
│       ├── render/               # draft.mp4, video.mp4, thumbnail.png
│       ├── review/               # contact sheets, review.md
│       ├── youtube.md
│       └── log.md                # per-stage timings and notes
└── docs/
    ├── licenses.md
    └── timings.md                # benchmark results on this Mac
```

## 6. `episode.json` schema

Implement this with pydantic in `pipeline/schema.py`. The fields below are a starting point; refine them if needed, but keep the idea.

```jsonc
{
  "id": "2026-11-20-mitti-ki-jaanch",
  "title_hi": "मिट्टी की जांच क्यों ज़रूरी है",
  "status": "script_approved",            // draft | script_approved | narrated | visuals_ready | draft_rendered | final_rendered | reviewed | packaged
  "video": { "width": 1920, "height": 1080, "fps": 30 },
  "voice": { "backend": "parler", "speaker": "...", "description": "..." },
  "scenes": [
    {
      "id": 1,
      "purpose": "hook",                  // hook | problem | explain | step | mistake | recap | cta
      "narration_display": "क्या आप हर साल बिना जांच के खाद डालते हैं?",   // shown in captions; digits allowed
      "narration_spoken": "क्या आप हर साल बिना जांच के खाद डालते हैं?",    // sent to TTS; numbers as words, pronunciation fixes applied
      "on_screen_text": "मिट्टी की जांच",  // optional short keyword overlay
      "visual": {
        "type": "image",                  // image | broll | graphic
        "image_prompt": "Indian farmer in a wheat field ...",   // for image
        "seed": 1234,
        "broll_id": null, "in_sec": null, "out_sec": null,      // for broll
        "template": null, "props": null                          // for graphic: TitleCard | KeyPoints | BigNumber
      },
      "sources": ["sources/shc-advisory.pdf#p3"],               // which source backs this scene's claims
      "audio": { "file": "audio/scene-01.wav", "duration_sec": 4.82 },
      "captions": [ { "text": "क्या आप हर साल", "start": 0.0, "end": 1.6 } ],
      "image_file": "images/scene-01.png"
    }
  ]
}
```

## 7. Stages and skills

Every stage is a CLI: `uv run python -m pipeline.<stage> episodes/<id> [--scene N] [--force]`. Each stage appends its duration and notes to the episode's `log.md`. Each skill's `SKILL.md` should be short: when to use it, the rules, and which commands to run. Put the logic in the scripts.

### 7.1 `make-episode` (orchestrator skill)
Walks through the stages in order, stops at the three checkpoints, and tells me exactly what to look at. If a stage fails, it fixes or retries that stage only. It never skips a checkpoint, even if I say "just do everything", unless I explicitly say to skip a named checkpoint for that episode.

### 7.2 `new_episode` + `hindi-script`
- `new_episode` creates the folder from a template, including `brief.md` with fields for topic, angle, crop, region, season and source notes.
- **You (Claude) write the script** in this session. No local LLM is needed for v0.
- Structure: hook in the first 10 seconds → problem → explanation → practical steps → common mistakes → recap → call to action (the CTA text comes from `config.yaml`).
- Scenes of about 6–12 seconds each, one idea per scene.
- Write `script.md` (a readable table: scene, Hindi narration, visual, sources) and fill `episode.json`.
- Build `narration_spoken` from `narration_display` using `text_normalize.py`: numbers to Hindi words ("25 किलो" → "पच्चीस किलो"), units, abbreviations, plus `pronunciation.yaml` overrides.
- `validate.py` checks the schema, rejects any remaining `[VERIFY`, warns if the total word count is outside the target range, and checks that every factual scene lists a source.
- **CHECKPOINT 1:** show me `script.md` and wait for approval or edits.

### 7.3 `narration`
- Default backend: **AI4Bharat Indic Parler-TTS** (Hugging Face). Use one of the Hindi speakers recommended on its model card, with a fixed voice description and fixed seed for consistency. Run on PyTorch MPS, with CPU fallback.
- Generate one file per scene. Resample to 48 kHz. Trim leading and trailing silence. Normalize loudness to the target in `config.yaml` (YouTube target about −14 LUFS integrated, measured over the full episode).
- Record each `duration_sec` in `episode.json`.
- Generate caption chunks (`captions.py`): split `narration_display` into chunks of at most N words (config value, default 6) at natural break points, and spread timing across the scene's audio in proportion to character length. Word-level alignment is a v1 feature.
- Keep the backend interface simple so ElevenLabs, Sarvam, or IndicF5 can be added later: `synthesize(text, voice_cfg, out_path) -> duration_sec`.
- After generating, play nothing automatically; tell me which files to listen to for a quick check (first two scenes plus any scene with numbers or English terms).

### 7.4 `visuals`
- For each scene, choose `broll`, `image`, or `graphic`. Prefer B-roll from the library when a clip really fits; use generated images where the library has nothing suitable; use graphics for numbers, lists and titles.
- **B-roll:** read `assets/broll/index.json`, pick a clip and in/out points that cover the scene duration (loop or slow down only if unavoidable). Never reuse the same clip segment twice in one episode.
- **Images:** generate with mflux (FLUX.1 schnell, quantized). Generate at a 16:9 size that is a multiple of 16 (e.g. 1344×768); Remotion scales it to cover 1080p, and the slow zoom hides the upscaling. Append the style suffix from `config.yaml` to every prompt. Store the seed.
- **Look at every generated image yourself.** Regenerate (new seed, adjusted prompt) if it shows non-Indian context, wrong crops, garbled text, distorted hands or faces, or doesn't match the narration. Make at most 3 attempts per scene, then flag it in `log.md` for me.
- **Graphics:** fill `template` and `props` (Hindi text, short).

### 7.5 `render`
- `render.py` syncs the episode's assets into `remotion/public/episodes/<id>/` (symlinks if Remotion handles them, otherwise copies) and calls `npx remotion render` with `episode.json` as input props.
- `--draft` renders at 540p (scale 0.5) for quick review. The final render is 1920×1080, 30 fps, H.264 video with AAC audio.
- Use the Mac's hardware encoder if Remotion supports it here; otherwise the default.
- **CHECKPOINT 2:** after the draft render, tell me where it is and wait. Apply my notes scene by scene, then do the final render.

### 7.6 `review`
- `review.py` extracts a frame every 2 seconds into contact sheets (ffmpeg tile filter, about 12 frames per sheet, with timestamps), checks the final duration against the sum of scenes, and measures integrated loudness.
- **You look at the contact sheets** and check: Devanagari renders correctly (no broken conjuncts or dotted circles), captions are readable and inside safe margins, text never covers the key part of an image, visuals match the narration, there are no black or frozen frames, and the watermark is present.
- Write `review/review.md` with pass/fail per item and the timestamps of any problems.

### 7.7 `package`
- Render a thumbnail from a `Thumbnail` Remotion composition: a large Hindi title of 3–5 words, a strong image from the episode, and the brand.
- Write `youtube.md`: Hindi title (under 70 characters), a Hindi description with a short summary, the sources list and a disclaimer, about 10 tags, and a reminder about YouTube's **altered or synthetic content** disclosure (flag "yes" if the video shows realistic generated people or scenes).
- **CHECKPOINT 3:** I approve and upload manually in v0.

### 7.8 `index-broll`
- For each new clip in `assets/broll/clips/`, run ffprobe (duration, resolution, fps) and extract 3 frames (start, middle, end). **You look at the frames** and write a description in English and Hindi, tags (crop, activity, setting, season, shot type), and quality notes into `index.json`.
- Record each clip's source and license (own footage, Pexels, Pixabay, etc.).

## 8. Remotion composition details

- `Episode` composition: total duration = sum over scenes of (audio duration + `scene_padding_sec`), in frames.
- Each scene is a `<Sequence>` with its audio and its visual component. Use simple crossfades between scenes (about 10 frames) via `@remotion/transitions`, accounting for the overlap in total duration.
- `KenBurnsImage`: slow zoom between 1.0 and about 1.12 with a gentle pan; the direction is chosen deterministically from the scene id so renders are reproducible.
- `BrollClip`: muted, trimmed to in/out points, `objectFit: cover`.
- `Captions`: bottom-centered, white text on a semi-transparent dark box, large enough to read on a phone (start at about 56 px at 1080p), at most 2 lines, inside title-safe margins.
- `OnScreenText`: a short keyword (1–4 words) in a top or side position, styled differently from captions.
- `Watermark`: logo from `assets/brand/` in a corner at low opacity.
- **Fonts:** bundle Noto Sans Devanagari locally in `remotion/public/fonts/` and load it from there, with no network fetch at render time. Make sure the composition waits for the font to load before rendering. Test with a still that includes these words: क्षेत्र, श्रमिक, द्वारा, कृषि, ज़्यादा, प्रधानमंत्री, ट्रैक्टर.
- Colors, font sizes and margins come from a theme object so they can be changed in one place.

## 9. `config.yaml` (starting values)

```yaml
video: { width: 1920, height: 1080, fps: 30, scene_padding_sec: 0.35 }
script: { target_words: [400, 650], cta_hi: "ऐसी और जानकारी के लिए चैनल को सब्सक्राइब करें।" }
tts:
  backend: parler
  model: ai4bharat/indic-parler-tts
  speaker: "<pick from model card>"
  description: "<clear, calm, moderate pace, close mic, no background noise>"
  seed: 42
  device: mps
  out_sample_rate: 48000
audio: { target_lufs: -14, true_peak_db: -1.5 }
images:
  backend: mflux
  model: schnell
  steps: 4
  quantize: 8
  width: 1344
  height: 768
  style_suffix: "photorealistic, rural India, natural daylight, documentary photography, no text, no watermark"
  max_attempts: 3
captions: { max_words_per_chunk: 6, font_size_px: 56 }
review: { frame_interval_sec: 2, frames_per_sheet: 12 }
```

## 10. Build phases and acceptance criteria

Stop after each phase, report, and wait for my go-ahead.

1. **Scaffold.** Repo structure, `CLAUDE.md`, `README.md`, `config.yaml`, uv project, `schema.py`, `common.py`, `new_episode.py`, `validate.py`, skill files (drafts).
   *Done when:* `new_episode` creates a folder and `validate` runs on a hand-written sample `episode.json`.
2. **Remotion with Hindi text.** Remotion project, theme, fonts, all scene and overlay components, using placeholder assets and dummy audio.
   *Done when:* a 20-second test render shows each component, and the Devanagari test words render correctly (show me a still).
3. **Narration.** Parler-TTS setup (ask me before downloading weights), `text_normalize.py`, `captions.py`, loudness normalization.
   *Done when:* three sample Hindi sentences, including numbers and English terms, are synthesized; record per-second timings in `docs/timings.md`.
4. **Images and B-roll.** mflux setup (ask before downloading), `images.py`, `broll.py`, `index-broll` skill. I'll put a few clips in `assets/broll/clips/`.
   *Done when:* 3 images are generated with timings recorded, and the index is built for the sample clips.
5. **Render, review, package.** `render.py` (draft and final), `review.py`, `package.py`, thumbnail composition.
6. **Demo episode end to end.** Use the `make-episode` skill on a topic I give you, with sources I provide. If I haven't provided sources, keep all claims general and mark specifics `[VERIFY]`, which will correctly stop the pipeline at checkpoint 1 so we can test that too.
   *Done when:* a 3–5 minute final video, a thumbnail, `youtube.md`, and a `log.md` with per-stage timings exist, and `docs/timings.md` summarizes which stages are slow on this Mac.

## 11. Out of scope for v0

Generated video clips, word-level karaoke captions, background music, YouTube API upload, topic ideation, Shorts (9:16), local LLM for scripts, AWS backends, LangGraph. Don't build these, but keep the backend interfaces open so they can be added.

## 12. v1 plan (context only; do not build now)

v1 goal: less manual work per episode, better quality, and publishing from the pipeline, still with human approval.

- **Ideation skill:** a `topics/backlog.md` ranked by season and crop calendar (rabi/kharif timing), questions farmers actually ask (from AgriGate's channels), government schemes and deadlines, and what performed well before. Each topic comes with a suggested angle and a list of sources needed.
- **Word-level captions:** align the known script text to the narration audio (e.g. Whisper word timestamps via mlx-whisper, or a forced aligner), with highlighted active words.
- **Bigger B-roll library:** a `fetch-stock` script for Pexels and Pixabay (API keys in `.env`, license and attribution stored per clip), plus a simple routine for field staff to contribute phone footage, which gets indexed by `index-broll`.
- **Music and sound:** royalty-free tracks in `assets/music/` with ducking under narration; light transition sounds.
- **Style skill from reference videos:** analyze 2–3 reference channels (frames at 2 fps plus transcript) and save pacing and layout rules as a `style-*` skill. Learn structure, never copy content or branding.
- **Shorts:** a 9:16 composition that re-cuts the strongest 30–60 seconds of an episode, with bigger captions.
- **YouTube upload:** YouTube Data API v3 with OAuth; upload as **private or scheduled** only after checkpoint 3; set the synthetic-content disclosure, title, description, tags, thumbnail. Note that uploads from an unverified API project are restricted to private until Google's audit, and daily quota limits the number of uploads.
- **Optional remote backends:** short generated clips (1–2 seconds) via ComfyUI with Wan or LTX-Video on an on-demand AWS GPU instance, or a paid API; an optional local LLM backend (Ollama) for drafts. Selected in `config.yaml`, nothing else changes.
- **Automated checks:** black-frame and freeze detection with ffmpeg, caption-overflow detection, loudness gate, all feeding `review.md`.
- **Feedback loop:** pull basic YouTube Analytics (views, retention) per episode into `topics/` to inform the next topics.
- **Later (v2):** once the skills are stable, move the proven flow into a LangGraph pipeline with interrupts at the same checkpoints, so it can run without an interactive session.

## 13. Open decisions to confirm with me

- My Mac's unified memory size (affects TTS and image model choices).
- **Remotion licensing:** Remotion is free only for individuals and very small companies; larger companies need a company license. Check the current terms and tell me. If it isn't possible, propose an MIT-licensed alternative (e.g. Revideo or Motion Canvas) before building phase 2.
- Brand assets (logo, colors) and the CTA line.
- Narrator voice: which Parler speaker I prefer after hearing samples.
- Topic and sources for the demo episode.