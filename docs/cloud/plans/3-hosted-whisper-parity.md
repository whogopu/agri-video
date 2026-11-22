# Plan 3: Hosted Whisper parity

**Goal:** replace the local mlx-whisper in `asr/` with a hosted Whisper large-v3-turbo API for take scoring and word timing, with no visible change in captions.

**What the asr worker does today** (`asr/asr_worker.py`): Whisper text, word timestamps (`word_timestamps=True`), plus librosa features computed locally: pitch range, end rise, median F0, max gap, silences. **Only the transcription part moves to an API.** The librosa features are cheap CPU work and stay in Python (later a Lambda).

**Candidates:** Groq Whisper large-v3-turbo (verbose_json with word timestamps; very cheap), OpenAI `whisper-1` (word timestamps; older model), fal.ai Whisper. Secondary: ElevenLabs Scribe, Sarvam STT (different models; only if Whisper APIs fall short).

## Steps

1. Split `asr/asr_worker.py` into transcription and features. Add `pipeline/asr_api.py`: `transcribe(wav, language="hi", prompt=None, words=True) -> {text, words:[{w,start,end}]}` per provider. Compute the librosa features in the main env or keep calling the worker with `transcribe: false`.
2. `config.yaml: narration.asr.backend` gains `groq` (and others); `take_scoring.measure()` and `word_align.time_scene_words()` dispatch on it (both currently accept `whisper | none`). Include the backend name in `word_align._cache_key` so cached timings don't mix.
3. Pass `initial_prompt` (word_align uses the scene text as a prompt) where the API supports `prompt`.
4. **Parity test** on 5 finished episodes' scene audio: compare local vs API.
   - CER vs `narration_spoken`: within ±0.5 points.
   - Word boundaries after `snap_to_speech`: median |Δ| < 40 ms, p95 < 120 ms.
   - Take choice: the same take wins in ≥ 90 % of sentences.
5. Render one draft (`pipeline.render --draft`) with API timings; the user checks the caption highlight on 2–3 scenes.
6. Record timings and cost in `docs/timings.md`; provider terms in `docs/licenses.md`.

## Acceptance

All thresholds in step 4 pass and the draft check looks right. Then set the API as default, keep `whisper` selectable.
