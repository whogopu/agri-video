# Setting up the pipeline on a new Mac

One script installs everything, checks each piece first, and can be re-run at any point: finished steps are skipped and downloads resume where they stopped.

**Needs:** a Mac with Apple Silicon (M1 or newer), 16 GB RAM, about 65 GB free disk, internet, and a [Hugging Face](https://huggingface.co) account.

## Quick version

On the **old** Mac (optional, saves a ~45 GB download and keeps your episode media):

```bash
cd ~/projects/agri-video
git status                                  # commit + push anything uncommitted first
./scripts/pack_for_new_mac.sh /Volumes/<SSD>/agri-video-transfer
```

On the **new** Mac:

```bash
xcode-select --install                      # only if git isn't installed yet; wait for it to finish
git clone <repo-url> ~/projects/agri-video
cd ~/projects/agri-video
./scripts/setup.sh --from /Volumes/<SSD>/agri-video-transfer   # or just ./scripts/setup.sh
```

If it stops, it prints why and what to do. Fix that and run the **same command** again.

When it ends with "Setup complete", open a new terminal and start the dashboard: `uv run python -m dashboard`.

## What the script does

| # | Step | Checks first | Installs if missing |
|---|---|---|---|
| 1 | This Mac | macOS, arm64, RAM, free disk | asks before going on if the disk is short |
| 2 | Xcode Command Line Tools | `xcode-select -p` | opens Apple's installer, then stops: re-run after it finishes |
| 3 | Homebrew | `/opt/homebrew/bin/brew` | official installer (asks for your Mac password once); adds it to `~/.zprofile` |
| 4 | ffmpeg, uv | `brew list` / on PATH | `brew install` |
| 5 | Node.js 20+ | `node -v` (nvm is honoured) | `brew install node` |
| 6 | Python 3.12 | `uv python find 3.12` | `uv python install 3.12` |
| 7 | Python envs: main, `tts-mlx/`, `asr/`, `vlm/` (+ `tts/` with `--with-parler`) | `uv sync --frozen` is a no-op when current, then an import test | exact versions from each `uv.lock` |
| 8 | mflux 0.24.0 | `uv tool list` | `uv tool install mflux==0.24.0` |
| 9 | Remotion | installed version = `package.json` | `npm ci`, headless browser, test assets |
| 10 | Episode media | stamp in `.setup/` | unpacks `agri-video-data.tar` from `--from` |
| 11 | Claude memory | — | copies `claude-memory/` without overwriting newer files |
| 12 | Models | Hugging Face login; files already cached | copies `hf-hub/` from `--from`, then `hf download` fills any gaps (resumes) |
| 13 | Checks | — | pytest, Remotion typecheck, a Devanagari test still, mflux, pipeline imports |
| 14 | `--smoke` only | — | one real TTS sentence and one real image |

Log of every command: `.setup/setup.log`.

## Options

```
--from DIR       transfer folder from pack_for_new_mac.sh
--skip-models    no model downloads now (stages fetch them on first use)
--with-parler    also the legacy Parler voices (tts/ env, 3.8 GB gated model)
--smoke          real TTS + image test at the end (~5 min)
--yes            no questions; Hugging Face login then comes from HF_TOKEN
```

## Models (~45 GB)

| Model | Used for | Size | Gated |
|---|---|---|---|
| maya-research/maya2-native | male voice `maya_vasant` (default) | 5 GB | no |
| maya-research/Veena + hubertsiuzdak/snac_24khz | female voice `veena_varun` | 7.7 GB | no |
| mlx-community/whisper-large-v3-turbo | scoring narration takes | 1.6 GB | no |
| mlx-community/Ministral-3-14B-Instruct-2512-4bit | shot-spec writer | 8.5 GB | no |
| black-forest-labs/flux-3-image-klein | images (only the folders mflux reads) | ~19 GB | **yes** |
| ai4bharat/indic-parler-tts | legacy voices (`--with-parler`) | 3.8 GB | **yes** |

For gated models, log in to huggingface.co with the account whose token you use, and click "Agree" on the model page. The script lists any you still need to accept and exits with code 2. Accept them, then re-run.

The Hugging Face token is **not** copied from the old Mac. Make a read token at <https://huggingface.co/settings/tokens>; the script asks for it once.

## Moving the transfer folder

- **External SSD** (fastest): run the pack script with the SSD as the destination, plug it into the new Mac, and pass its path to `--from`.
- **Over the network**: turn on Remote Login on the new Mac (System Settings → General → Sharing), then from the old Mac run `rsync -a --partial --progress <transfer-folder>/ <user>@<new-mac>.local:agri-video-transfer/`. It is resumable, so run it again if it stops.

## Things that don't move automatically

- Uncommitted changes: commit and push before cloning.
- Secrets: the Hugging Face token, and `.env` if you make one.
- The old bake-off and trial models (`vlm/models/`, `~/mflux-models/`, other image models). Production doesn't need them.
- If your username or folder differs on the new Mac, Claude memory still lands in the right place, because the script works out the path from where the repo is.
