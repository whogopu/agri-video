#!/bin/bash
# One-step, re-runnable setup for the AgriGate video pipeline on a fresh Apple Silicon Mac.
#
#   ./scripts/setup.sh                       # everything, models downloaded from Hugging Face
#   ./scripts/setup.sh --from /Volumes/SSD/agri-video-transfer   # restore media + models + Claude memory
#                                            # packed on the old Mac by scripts/pack_for_new_mac.sh
#
# Every step first checks whether its work is already done and skips it if so. If a step fails, fix the
# cause it prints and run the same command again: finished steps are skipped and downloads resume.
# Full guide: docs/SETUP_NEW_MAC.md
#
# Options:
#   --from DIR       transfer folder from pack_for_new_mac.sh (any of: agri-video-data.tar, hf-hub/, claude-memory/)
#   --skip-models    don't download model weights (pipeline stages will download on first use)
#   --with-parler    also set up the legacy Parler TTS env (tts/) and its gated model (3.8 GB)
#   --smoke          at the end, run a real TTS sentence and a real image (about 5 min, uses the models)
#   --yes            don't ask questions (Hugging Face login must then come from HF_TOKEN)
#   -h, --help

set -u -o pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$REPO/.setup"
LOG="$STATE/setup.log"
mkdir -p "$STATE"

FROM=""; SKIP_MODELS=0; WITH_PARLER=0; SMOKE=0; YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="${2:-}"; shift ;;
    --skip-models) SKIP_MODELS=1 ;;
    --with-parler) WITH_PARLER=1 ;;
    --smoke) SMOKE=1 ;;
    --yes|-y) YES=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)"; exit 1 ;;
  esac
  shift
done
if [ -n "$FROM" ] && [ ! -d "$FROM" ]; then echo "--from: folder not found: $FROM"; exit 1; fi

# ---------- output helpers ----------
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'; else B=""; G=""; Y=""; R=""; N=""; fi
STEP_NO=0
PENDING=()          # things the user still has to do (shown at the end)
step()  { STEP_NO=$((STEP_NO+1)); echo; echo "${B}[$STEP_NO] $*${N}"; echo "=== [$STEP_NO] $* ($(date '+%F %T'))" >> "$LOG"; }
ok()    { echo "  ${G}✓${N} $*"; }
skip()  { echo "  ${G}✓${N} $* ${Y}(already done)${N}"; }
info()  { echo "  · $*"; }
warn()  { echo "  ${Y}!${N} $*"; }
die()   {
  echo "  ${R}✗ $*${N}"
  echo
  echo "${R}Setup stopped at step $STEP_NO.${N} Fix the problem above, then run the same command again;"
  echo "finished steps are skipped. Log: $LOG"
  exit 1
}
run()   { echo "  \$ $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; }       # quiet, output to the log
loud()  { echo "  \$ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"; }
have()  { command -v "$1" >/dev/null 2>&1; }
ask()   { [ "$YES" = 1 ] && return 0; read -r -p "  $1 [Y/n] " a; case "$a" in n|N|no) return 1 ;; *) return 0 ;; esac; }
add_line_once() {  # add_line_once FILE LINE
  touch "$1"; grep -qxF "$2" "$1" || { echo "$2" >> "$1"; info "added to $1: $2"; }
}

echo "${B}AgriGate video pipeline setup${N}  (repo: $REPO)"
echo "Log: $LOG"

# ---------- 1. machine ----------
step "Check this Mac"
[ "$(uname -s)" = "Darwin" ] || die "macOS only (MLX models need Apple Silicon)."
[ "$(uname -m)" = "arm64" ] || die "Apple Silicon (arm64) needed; this is $(uname -m). If this is Terminal under Rosetta, open a native Terminal."
ok "macOS $(sw_vers -productVersion), $(uname -m)"
MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
if [ "$MEM_GB" -lt 16 ]; then warn "${MEM_GB} GB RAM: image generation needs about 9 GB free; 16 GB is the tested minimum."; else ok "${MEM_GB} GB RAM"; fi
FREE_GB=$(df -g "$HOME" | awk 'NR==2 {print $4}')
NEED_GB=15; [ "$SKIP_MODELS" = 0 ] && NEED_GB=65
if [ "$FREE_GB" -lt "$NEED_GB" ]; then
  warn "only ${FREE_GB} GB free; about ${NEED_GB} GB needed (tools ~8 GB, models ~45 GB, media ~4 GB)."
  ask "Continue anyway?" || die "free up disk space, or re-run with --skip-models."
else ok "${FREE_GB} GB free disk (need ~${NEED_GB} GB)"; fi

# ---------- 2. Xcode command line tools (git, compilers) ----------
step "Xcode Command Line Tools"
if xcode-select -p >/dev/null 2>&1 && have git; then
  skip "installed at $(xcode-select -p)"
else
  info "opening the Apple installer; click Install and wait for it to finish (5-15 min)."
  xcode-select --install >/dev/null 2>&1 || true
  die "finish the Command Line Tools install in the window that opened, then run this script again."
fi

# ---------- 3. Homebrew ----------
step "Homebrew"
if [ -x /opt/homebrew/bin/brew ]; then
  skip "Homebrew $(/opt/homebrew/bin/brew --version | head -1 | awk '{print $2}')"
else
  info "installing Homebrew (asks for your Mac password once)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || die "Homebrew install failed. See https://brew.sh"
  ok "Homebrew installed"
fi
eval "$(/opt/homebrew/bin/brew shellenv)"
add_line_once "$HOME/.zprofile" 'eval "$(/opt/homebrew/bin/brew shellenv)"'

# ---------- 4. command line tools from Homebrew ----------
step "ffmpeg and uv (Homebrew)"
for pkg in ffmpeg uv; do
  if brew list --formula "$pkg" >/dev/null 2>&1 || have "$pkg"; then
    skip "$pkg ($(command -v "$pkg"))"
  else
    loud brew install "$pkg" || die "brew install $pkg failed (check internet, then re-run)."
    ok "$pkg installed"
  fi
done
have ffprobe || die "ffprobe missing even though ffmpeg is installed; try: brew reinstall ffmpeg"

# ---------- 5. Node 20+ (Remotion) ----------
step "Node.js 20+"
node_major() { node -v 2>/dev/null | sed 's/^v//; s/\..*//'; }
# nvm users: load nvm so its node counts
if ! have node && [ -s "$HOME/.nvm/nvm.sh" ]; then . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1; fi
if have node && [ "$(node_major)" -ge 20 ] 2>/dev/null; then
  skip "node $(node -v) ($(command -v node))"
else
  [ -n "$(node_major)" ] && warn "node $(node -v) is too old"
  loud brew install node || die "brew install node failed."
  hash -r
  [ "$(node_major)" -ge 20 ] || die "node is still older than 20 ($(command -v node)); remove the old one from PATH."
  ok "node $(node -v)"
fi

# ---------- 6. Python 3.12 (managed by uv) ----------
step "Python 3.12 (uv-managed)"
if uv python find 3.12 >/dev/null 2>&1; then
  skip "$(uv python find 3.12)"
else
  loud uv python install 3.12 || die "uv python install 3.12 failed."
  ok "Python 3.12 installed"
fi
export PATH="$HOME/.local/bin:$PATH"
run uv tool update-shell || true      # puts ~/.local/bin on PATH in your shell profile (idempotent)

# ---------- 7. Python environments ----------
# uv sync --frozen installs exactly what uv.lock says; when nothing changed it finishes in about a second.
sync_env() {  # sync_env DIR LABEL IMPORTS
  local dir="$1" label="$2" imports="$3"
  info "$label: uv sync ($dir)"
  ( cd "$REPO/$dir" && run uv sync --frozen ) || die "uv sync failed in $dir/ (see $LOG). Check internet and re-run."
  ( cd "$REPO/$dir" && run uv run --frozen python -c "import $imports" ) \
    || die "$label env installed but 'import $imports' fails (see $LOG). Try: rm -rf $dir/.venv and re-run."
  ok "$label ready ($dir/.venv)"
}
step "Python environments"
sync_env .       "main pipeline"                  "yaml, pydantic, PIL, numpy, soundfile, pytest"
sync_env tts-mlx "TTS (Maya2 male, Veena female)" "mlx_audio, snac, torch, huggingface_hub"
sync_env asr     "take scoring (Whisper)"         "mlx_whisper, librosa"
sync_env vlm     "local LLM / VLM (shot specs)"   "mlx_vlm"
if [ "$WITH_PARLER" = 1 ]; then
  sync_env tts   "legacy Parler TTS"              "parler_tts"
else
  info "legacy Parler env (tts/) skipped; add --with-parler if you need the rohit/aman voices"
fi

# ---------- 8. mflux (image generation) ----------
step "mflux 0.24.0 (FLUX.3 Klein runner)"
if uv tool list 2>/dev/null | grep -q '^mflux v0\.24\.0'; then
  skip "mflux 0.24.0"
else
  loud uv tool install --force mflux==0.24.0 || die "uv tool install mflux==0.24.0 failed."
  ok "mflux 0.24.0 installed"
fi
have mflux-generate-flux3 && have mflux-generate-flux3-edit \
  || die "mflux-generate-flux3 not on PATH; open a new terminal (PATH was updated) and re-run."
ok "$(command -v mflux-generate-flux3)"

# ---------- 9. Remotion (video rendering) ----------
step "Remotion (npm packages, headless browser, test assets)"
cd "$REPO/remotion" || die "remotion/ folder missing"
want_ver=$(node -p "require('./package.json').dependencies.remotion")
have_ver=$(node -p "try{require('./node_modules/remotion/package.json').version}catch(e){''}" 2>/dev/null)
if [ "$have_ver" = "$want_ver" ] && [ -x node_modules/.bin/remotion ]; then
  skip "npm packages (remotion $have_ver)"
else
  loud npm ci --no-audit --no-fund || die "npm ci failed in remotion/ (see $LOG)."
  ok "npm packages installed (remotion $want_ver)"
fi
run npx remotion browser ensure || die "Remotion could not download its headless browser (see $LOG)."
ok "headless browser ready"
if [ -f public/brand/logo.png ] && [ -d public/test ]; then
  skip "test assets (public/brand, public/test)"
else
  run npm run test-assets || die "npm run test-assets failed (see $LOG)."
  ok "test assets made"
fi
cd "$REPO"

# ---------- 10. media from the old Mac ----------
step "Episode media from the old Mac (optional)"
TAR=""; [ -n "$FROM" ] && [ -f "$FROM/agri-video-data.tar" ] && TAR="$FROM/agri-video-data.tar"
if [ -z "$TAR" ]; then
  info "no --from DIR/agri-video-data.tar given; skipped (episode audio/images/renders are not in git)"
else
  stamp="$(stat -f '%z-%m' "$TAR")"
  if [ "$(cat "$STATE/data-restored" 2>/dev/null)" = "$stamp" ]; then
    skip "media restored from $TAR"
  else
    info "unpacking $(du -h "$TAR" | cut -f1) into the repo (re-running is safe)"
    tar -xf "$TAR" -C "$REPO" || die "unpacking $TAR failed (disk full? partial copy?)."
    echo "$stamp" > "$STATE/data-restored"
    ok "media restored"
  fi
fi

# ---------- 11. Claude Code memory ----------
step "Claude Code project memory (optional)"
MEM_SRC=""; [ -n "$FROM" ] && [ -d "$FROM/claude-memory" ] && MEM_SRC="$FROM/claude-memory"
MEM_DST="$HOME/.claude/projects/$(printf '%s' "$REPO" | sed 's/[^A-Za-z0-9]/-/g')/memory"
if [ -z "$MEM_SRC" ]; then
  info "no --from DIR/claude-memory; skipped"
else
  mkdir -p "$MEM_DST"
  # --ignore-existing: never overwrite memory written on this Mac
  rsync -a --ignore-existing "$MEM_SRC/" "$MEM_DST/" || die "copying Claude memory failed."
  ok "memory in $MEM_DST ($(ls "$MEM_DST" | wc -l | tr -d ' ') files)"
fi

# ---------- 12. models ----------
HF() { ( cd "$REPO/tts-mlx" && uv run --frozen hf "$@" ); }
step "Model weights"
if [ -n "$FROM" ] && [ -d "$FROM/hf-hub" ]; then
  info "copying models from $FROM/hf-hub (resumable)"
  mkdir -p "$HOME/.cache/huggingface/hub"
  rsync -a --partial "$FROM/hf-hub/" "$HOME/.cache/huggingface/hub/" || die "copying models failed (disk full?)."
  ok "models copied into ~/.cache/huggingface/hub"
fi

if [ "$SKIP_MODELS" = 1 ]; then
  info "--skip-models: not downloading; stages download what they need on first use"
else
  # Hugging Face login: needed for the gated FLUX.3 Klein (and Parler) models.
  if HF auth whoami 2>&1 | grep -qi "not logged in"; then
    if [ -n "${HF_TOKEN:-}" ]; then
      run HF auth login --token "$HF_TOKEN" || die "hf auth login with HF_TOKEN failed."
    elif [ "$YES" = 1 ]; then
      die "not logged in to Hugging Face; set HF_TOKEN=<read token> or run without --yes."
    else
      echo "  Hugging Face login needed (FLUX.3 Klein is a gated model)."
      echo "  Make a READ token at https://huggingface.co/settings/tokens and paste it below."
      HF auth login || die "Hugging Face login failed."
    fi
  fi
  ok "Hugging Face: logged in as $(HF auth whoami 2>/dev/null | head -1)"

  # download REPO [include patterns...]; already-complete files are skipped, partial ones resume.
  fetch() {
    local repo="$1" what="$2"; shift 2
    local args=()
    for p in "$@"; do args+=(--include "$p"); done
    info "$repo  ($what)"
    if HF download "$repo" ${args[@]+"${args[@]}"} >> "$LOG" 2>&1; then
      ok "$repo"
    elif tail -40 "$LOG" | grep -qiE "gated|403|401|restricted|awaiting"; then
      warn "$repo is gated: accept its terms at https://huggingface.co/$repo (same account), then re-run"
      PENDING+=("Accept the model terms at https://huggingface.co/$repo, then re-run ./scripts/setup.sh")
    else
      die "download of $repo failed (see $LOG). Re-run to resume."
    fi
  }
  fetch maya-research/maya2-native                   "male voice maya_vasant, ~5 GB"
  fetch maya-research/Veena                          "female voice veena_varun, ~7.6 GB"
  fetch hubertsiuzdak/snac_24khz                     "audio codec for Veena, 0.1 GB"
  fetch mlx-community/whisper-large-v3-turbo         "take scoring, 1.6 GB"
  fetch mlx-community/Ministral-3-14B-Instruct-2512-4bit "shot-spec writer, 8.5 GB"
  fetch black-forest-labs/flux-3-image-klein         "images, ~19 GB (gated)" \
        "*.json" "NOTICE.md" "transformer/*" "text_encoder/*" "vae/*"
  if [ "$WITH_PARLER" = 1 ]; then
    fetch ai4bharat/indic-parler-tts                 "legacy Parler voice, 3.8 GB (gated)"
  fi
fi

# ---------- 13. checks ----------
step "Checks"
( cd "$REPO" && run uv run --frozen pytest -q ) || die "unit tests fail (see $LOG)."
ok "unit tests pass ($(grep -Eo '[0-9]+ passed' "$LOG" | tail -1))"
( cd "$REPO/remotion" && run npx tsc --noEmit ) || die "Remotion typecheck fails (see $LOG)."
ok "Remotion typecheck"
( cd "$REPO/remotion" && run npx remotion still src/index.ts FontTest out/font-test.png ) \
  || die "Remotion test still failed (see $LOG)."
ok "Devanagari test still: remotion/out/font-test.png (open it: the Hindi must look right)"
run mflux-generate-flux3 --help || die "mflux-generate-flux3 --help failed."
ok "mflux runs"
( cd "$REPO" && run uv run --frozen python -m pipeline.validate --help ) || die "pipeline import failed."
ok "pipeline imports"

# ---------- 14. optional real smoke test ----------
if [ "$SMOKE" = 1 ]; then
  step "Smoke test with real models (one at a time)"
  ( cd "$REPO" && loud uv run --frozen python -m pipeline.tts_try --voices maya_vasant --out samples/setup-smoke ) \
    || die "TTS smoke test failed (see $LOG)."
  ok "TTS: samples/setup-smoke/"
  ( cd "$REPO" && loud uv run --frozen python -m pipeline.images \
      --prompt "Indian farmer standing in a green wheat field, morning light" --seed 1 --out samples/setup-smoke/image.png ) \
    || die "image smoke test failed (see $LOG)."
  ok "image: samples/setup-smoke/image.png"
fi

# ---------- done ----------
echo
if [ ${#PENDING[@]} -gt 0 ]; then
  echo "${Y}${B}Setup finished, with things left for you:${N}"
  for p in "${PENDING[@]}"; do echo "  - $p"; done
  exit 2
fi
echo "${G}${B}Setup complete.${N} Open a new terminal (PATH changed), then:"
echo "  uv run python -m dashboard            # control room at http://127.0.0.1:8765"
echo "  ./scripts/setup.sh --smoke            # optional: real TTS + image test (~5 min)"
