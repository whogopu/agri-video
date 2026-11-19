# Licenses

Rule: company project, so **no non-commercial licenses**. Check before adopting any model or library; record it here.

| Component | Used for | License | Commercial OK? | Checked | Notes |
|---|---|---|---|---|---|
| pydantic | episode schema | MIT | yes | 2026-11-19 | |
| PyYAML | config | MIT | yes | 2026-11-19 | |
| numpy 2.x, soundfile 0.14 | take edge cleaning (main env) | BSD-3 / BSD-3 | yes | 2026-11-19 | |
| pytest | tests (dev only) | MIT | yes | 2026-11-19 | |
| Pillow 13.0.0 | contact-sheet timestamps | MIT-CMU (HPND) | yes | 2026-11-19 | |
| uv | env/deps tool | MIT / Apache-2.0 | yes | 2026-11-19 | |
| React / React DOM 19.3.1 | Remotion UI | MIT | yes | 2026-11-19 | |
| TypeScript 7.0.2 | dev only | Apache-2.0 | yes | 2026-11-19 | |
| @remotion/transitions, @remotion/cli 4.0.545 | rendering | Remotion License | see Remotion row | 2026-11-19 | same license as `remotion` |
| **Remotion** | rendering | Remotion License (source-available) | **only with a Company License** if a for-profit with >3 people | 2026-11-19 | Free for individuals, for-profits with ≤3 employees, and non-profits. Otherwise: Creators $25/seat/month, Automators $0.01/render (min $100/month), Enterprise from $500/month. Unclear whether a scripted local pipeline counts as "automation"; confirm with Remotion. License changes announced for Remotion 5.0. **Decision (2026-11-19): using the free individual license — the project is currently a personal learning/educational project. If it becomes a company/commercial channel, buy a Company License (Creators, $25/seat/month) before publishing.** Sources: [LICENSE.md](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md), [pricing](https://www.remotion.dev/docs/license/pricing) |
| ai4bharat/indic-parler-tts (weights) | TTS model | Apache-2.0 | yes | 2026-11-19 | gated on Hugging Face (accept terms + login). 0.9B params, F32 (~3.6 GB). [model card](https://huggingface.co/ai4bharat/indic-parler-tts) |
| parler-tts (code, commit d108732) | TTS library | Apache-2.0 | yes | 2026-11-19 | isolated env `tts/` because it pins transformers==4.46.1 |
| transformers 4.46.1 / torch / torchaudio | TTS runtime | Apache-2.0 / BSD-3 / BSD-2 | yes | 2026-11-19 | `tts/` env only |
| descript-audio-codec, descript-audiotools | parler-tts deps | MIT | yes | 2026-11-19 | `tts/` env only |
| soundfile | WAV writing | BSD-3 | yes | 2026-11-19 | `tts/` env only |
| mlx-whisper 0.4.3, mlx 0.32.4 | narration take scoring (transcribe each take) | MIT | yes | 2026-11-19 | isolated env `asr/`, called as a subprocess |
| **openai/whisper-large-v3-turbo** (`mlx-community/whisper-large-v3-turbo`) | ASR model for take scoring | MIT | yes | 2026-11-19 | ~1.6 GB. Only used to rank takes, never published |
| librosa 1.0.1 (+ numba BSD-2, scipy BSD-3) | pitch / pause measurement of takes | ISC | yes | 2026-11-19 | `asr/` env only |
| mlx-audio 0.6.6 | runs Maya2 / Chatterbox on Apple Silicon | MIT | yes | 2026-11-19 | isolated env `tts-mlx/` |
| mlx-lm 0.32.2, snac 1.2.1, torch 2.15 | Indic-Speak / Veena runner, SNAC codec | MIT / MIT / BSD-3 | yes | 2026-11-19 | `tts-mlx/` env only; SNAC weights `hubertsiuzdak/snac_24khz` MIT |
| **Maya2 Native** (`maya-research/maya2-native`) | TTS candidate, 20 built-in voices | Apache-2.0 | yes | 2026-11-19 | components: Qwen3-1.7B-Base Apache-2.0, **Kyutai Mimi codec CC-BY-4.0 (attribution required)**, SpeechBrain ECAPA Apache-2.0. ~5 GB |
| **Chatterbox Multilingual v3** (`mlx-community/chatterbox-multilingual-v3`) | TTS candidate, copies a reference voice | MIT | yes | 2026-11-19 | every clip carries an imperceptible PerTh watermark. Reference clips must be **synthetic** (our own Parler takes), never a real person (CLAUDE.md, user decision 2026-11-19) |
| **Indic-Speak** (Bodhan AI; community MLX bf16 `iniquitous/indic-speak-mlx-bf16`) | TTS candidate, built-in voices + style tags | **Indic Open Model License v1.0** + Llama 3.2 Community License | **yes, with conditions** | 2026-11-19 | Commercial use royalty-free. Hosting the model for third parties needs Bodhan's written approval (we don't host; publishing generated audio isn't hosting). Attribution when the model itself is made available; prohibited-uses list (§10) applies to outputs; arbitration in India; separate licence above 500M MAU / US$250M revenue. Llama 3.2: commercial OK, acceptable-use policy. **Have the user/legal read §10 before adopting.** We run our own worker; repo code is not executed and the Vocos checkpoint loads with `weights_only=True`. `tts-mlx/vocos_decoder.py` is vendored from the repo (same licence, internal use) |
| **Veena** (`maya-research/Veena`) | TTS candidate | Apache-2.0 | yes | 2026-11-19 | training data proprietary. All 11 speaker tokens measured 245–268 Hz (no low male voice); not piloted |
| Voxtral TTS (Mistral), XTTS-v2 (Coqui), MMS-TTS (Meta) | — | CC BY-NC 4.0 / CPML / CC BY-NC 4.0 | **no** | 2026-11-19 | non-commercial: don't use |
| rumik-oss-1 | — | unclear (reported non-production) | **no** until checked | 2026-11-19 | |
| VibeVoice-Hindi-7B (community, `tarun7r`) | — | MIT, but card says research use / not for commercial use without testing | not used | 2026-11-19 | needs a reference voice, CUDA example, ~36 GB F32 weights; doesn't fit 16 GB without quantization |
| mflux 0.24.0 | image generation runner (MLX) | MIT | yes | 2026-11-19 | `uv tool install mflux==0.24.0` (per user, not system-wide) |
| **FLUX.2 [klein] 4B** (black-forest-labs/FLUX.2-klein-4B) | image model (in use) | Apache-2.0 | yes | 2026-11-19 | using the pre-quantized `mflux-community/flux2-klein-4b-mflux-q4` (Apache-2.0, 4.6 GB). The model card lists out-of-scope uses (deceptive content, NCII, harassment) |
| FLUX.1 [schnell] | image model (fallback) | Apache-2.0 | yes | 2026-11-19 | `mflux-community/flux-1-schnell-mflux-q4` is 9.6 GB. Not downloaded |
| FLUX.1 [dev], FLUX.2 klein **9B**, flux-3-image-klein | — | non-commercial / other | **no** | 2026-11-19 | don't use |
| Noto Sans Devanagari (variable) | captions/graphics font | SIL OFL 1.1 | yes | 2026-11-19 | bundled in `remotion/public/fonts/` with `OFL.txt`; from google/fonts repo |
| B-roll clips | footage | per clip (`assets/broll/index.json: license`) | checked per clip | — | `broll check` and `validate` reject clips without a license |
| ffmpeg 9.0.2 (Homebrew) | media processing | LGPL/GPL (Homebrew build) | yes, as an external CLI | 2026-11-19 | called as a separate program, not linked. Homebrew build has **no `drawtext` filter** (no freetype) |
