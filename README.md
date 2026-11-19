# agri-video

AgriGate's pipeline for Hindi educational videos for farmers (YouTube, 3–5 min). An AI narrator explains a topic in Hindi over B-roll, slow-zoom images, simple graphics and Hindi captions. Each episode is produced in a Claude Code session with three human checkpoints; the media work runs locally on a Mac.

> Status: **v0 complete**: all 6 phases built; demo episode `episodes/2026-11-19-mitti-ki-jaanch`. Narration, visuals and rendering arrive in later phases; see `PROJECT_BRIEF.md` §10.

## Setup

Requirements: macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/), Node 20+, Homebrew.

```bash
uv sync              # creates .venv with Python 3.12
uv run pytest -q     # phase 1 tests
```

```bash
brew install ffmpeg
cd remotion && npm install
npm run test-assets                       # placeholder assets for the component test
npx remotion still src/index.ts FontTest out/font-test.png   # Devanagari check
npx remotion render src/index.ts Episode out/test.mp4        # 20 s component test
npx remotion studio                       # live preview in the browser
```

Narration (Indic Parler-TTS, separate env because it pins old `transformers`):

1. Accept the model terms at https://huggingface.co/ai4bharat/indic-parler-tts (logged in to Hugging Face).
2. Create a read token at https://huggingface.co/settings/tokens, then:
   ```bash
   cd tts && uv sync && uv run hf auth login   # paste the token
   cd .. && uv run python -m pipeline.tts_try --speakers Rohit Divya   # first run downloads ~3.6 GB
   ```

Images (FLUX.2 klein 4B, 4-bit, ~4.6 GB download on first use):
```bash
uv tool install mflux==0.24.0
uv run python -m pipeline.images --prompt "Indian farmer in a wheat field" --out samples/test.png
```

B-roll: put clips in `assets/broll/clips/`, then ask Claude to run the `index-broll` skill (or `uv run python -m pipeline.broll index`). Every clip needs a known source and license before it can be used.

## Making an episode

1. Create the folder:
   ```bash
   uv run python -m pipeline.new_episode mitti-ki-jaanch --topic "soil testing"              # long video (16:9, 3–5 min)
   uv run python -m pipeline.new_episode urea-ka-sahi-samay --format short --topic "..."     # YouTube Short (9:16, 30–60 s)
   uv run python -m pipeline.new_episode mitti-ki-jaanch --voice aman                       # Aman instead of the default Rohit
   ```
2. Fill in `episodes/<id>/brief.md` and put your source files (advisories, PDFs, notes) in `episodes/<id>/sources/`. **Only facts from these files go into the video.**
3. In Claude Code, run the `make-episode` skill (e.g. "make the episode in episodes/<id>"). Claude will:
   - write `script.md` + `episode.json` → **Checkpoint 1: you approve the script**
   - generate narration, pick/generate visuals, render a 540p draft → **Checkpoint 2: you review the draft**
   - render 1080p, review frames, make thumbnail + `youtube.md` → **Checkpoint 3: you approve and upload**

Check an episode at any time:

```bash
uv run python -m pipeline.validate episodes/<id>
```

Any `[VERIFY: ...]` left in the script blocks the pipeline. Resolve it by adding a source or removing the claim.

Technical details (architecture, control flow, decisions, future plans): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Layout

| Path | What |
|---|---|
| `config.yaml` | all settings and backend choices |
| `pronunciation.yaml` | word → spoken-form fixes for TTS |
| `pipeline/` | one Python module per stage |
| `remotion/` | Remotion compositions; styling in `src/theme.ts` |
| `assets/brand/` | logo and colors |
| `assets/broll/` | B-roll clips + `index.json` |
| `episodes/<date>-<slug>/` | one folder per episode |
| `.claude/skills/` | Claude Code skills for each stage |
| `docs/licenses.md` | license check for every dependency |
| `docs/timings.md` | benchmarks on this Mac |
