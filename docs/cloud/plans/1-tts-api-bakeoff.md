# Plan 1: TTS API bake-off

**Goal:** find out whether a hosted Hindi voice is as good as `maya_vasant` (male) and `veena_varun` (female), which the user chose on 2026-11-19 after a 5-model listening test. If one is, narration needs no GPU in the cloud.

**Candidates** (verify prices on vendor pages at run time):
- **Sarvam Bulbul** (Indian vendor, Hindi-first, ~₹15–30 per 10k chars).
- **ElevenLabs v3** (multilingual, expressive; strong benchmark showing for Hindi).
- **Gemini TTS** (Google; controllable style by prompt).
- Optional: **OpenAI gpt-4o-mini-tts**, Azure Hindi neural voices as a cheap floor.

**Constraint:** only the vendors' stock voices or voices designed from a text description. No cloning of any real person. A voice-design clip made from our own synthetic voice is allowed (user decision 2026-11-19), but stock voices first.

## Steps

1. **Backends.** In `pipeline/tts_backends.py` add `SarvamBackend`, `ElevenLabsBackend`, `GeminiTTSBackend` implementing `synthesize_many(jobs) -> list[TTSResult]` (same contract as `MlxAudioBackend`). Use plain HTTPS: add `httpx` (BSD-3; not yet a dependency) and record it in `docs/licenses.md`. Keys from env vars `SARVAM_API_KEY`, `ELEVENLABS_API_KEY`, `GEMINI_API_KEY`. Register in `BACKENDS`.
   - Map our delivery markup: `|` / `||` → the vendor's pause syntax (SSML `<break>` for Sarvam/Azure, `...` or tags for ElevenLabs v3, natural-language direction for Gemini). `{slow|warm|firm|question}` → vendor style/speed parameter or prompt prefix. Keep the mapping in one function per backend, unit-tested.
   - Takes: request N takes by varying `seed` where supported (ElevenLabs, Gemini); for deterministic APIs, takes = 1 and note it.
   - Write raw WAV; `narration.py` already post-processes.
2. **Config.** Add voices to `config.yaml: tts.voices`, e.g. `sarvam_male`, `sarvam_female`, `eleven_male`, `eleven_female`, `gemini_male`, `gemini_female`, each with `backend`, `voice`/`speaker`, `lang: hi`, and a measured `wpm` (fill after the first run).
3. **Cost logging.** Each backend returns characters billed; add a `tts_usd_per_1k_chars` per voice in config and write cost into the stage log via `stage_timer` notes.
4. **Audition set.** Reuse the 4 pilot scenes used for the original voice test (see `pipeline/tts_try.py` and `docs/timings.md` for which). Same `narration_spoken` text for every voice, generated through `pipeline.text_normalize` so numbers are words.
5. **Run.** `uv run python -m pipeline.tts_try --voices maya_vasant veena_varun sarvam_male ...` (extend `tts_try` if it can't take new backends). Then score every take with the existing Whisper scorer (`pipeline/take_scoring.py`): CER, gaps, pitch range.
6. **Blind listening.** Build a blind page (copy the pattern of `/bakeoff` in `dashboard/static/bakeoff.html`, audio instead of images): random labels, user rates each clip on clarity, naturalness, correct pronunciation of यूरिया / DAP / numbers, tone (सलाहकार, not announcer). Reveal after rating.
7. **Report.** `docs/cloud/tts-bakeoff.md`: table per voice (CER, wpm, cost/episode at 700 words, latency, blind score), listening notes, licence/terms, recommendation.

## Acceptance

- A hosted voice is adopted only if the user prefers it, or rates it equal, to the current voice for its gender in the blind test **and** its median CER is no worse than the current voice's by more than 1 point.
- Pronunciation fixes in `pronunciation.yaml` still apply (they run before TTS); note any vendor that needs extra fixes.

## Out of scope

Switching production voices. That is a user decision after the report; then update `config.yaml` default and `CLAUDE.md` Voices line.
