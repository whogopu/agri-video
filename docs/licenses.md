# Licenses

Rule: company project, so **no non-commercial licenses**. Check before adopting any model or library; record it here.

| Component | Used for | License | Commercial OK? | Checked | Notes |
|---|---|---|---|---|---|
| pydantic | episode schema | MIT | yes | 2026-11-19 | |
| PyYAML | config | MIT | yes | 2026-11-19 | |
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
| mflux 0.24.0 | image generation runner (MLX) | MIT | yes | 2026-11-19 | `uv tool install mflux==0.24.0` (per user, not system-wide) |
| **FLUX.2 [klein] 4B** (black-forest-labs/FLUX.2-klein-4B) | image model (in use) | Apache-2.0 | yes | 2026-11-19 | using the pre-quantized `mflux-community/flux2-klein-4b-mflux-q4` (Apache-2.0, 4.6 GB). The model card lists out-of-scope uses (deceptive content, NCII, harassment) |
| FLUX.1 [schnell] | image model (fallback) | Apache-2.0 | yes | 2026-11-19 | `mflux-community/flux-1-schnell-mflux-q4` is 9.6 GB. Not downloaded |
| FLUX.1 [dev], FLUX.2 klein **9B**, flux-3-image-klein | — | non-commercial / other | **no** | 2026-11-19 | don't use |
| Noto Sans Devanagari (variable) | captions/graphics font | SIL OFL 1.1 | yes | 2026-11-19 | bundled in `remotion/public/fonts/` with `OFL.txt`; from google/fonts repo |
| B-roll clips | footage | per clip (`assets/broll/index.json: license`) | checked per clip | — | `broll check` and `validate` reject clips without a license |
| ffmpeg 9.0.2 (Homebrew) | media processing | LGPL/GPL (Homebrew build) | yes, as an external CLI | 2026-11-19 | called as a separate program, not linked. Homebrew build has **no `drawtext` filter** (no freetype) |
