#!/bin/bash
# Run on the OLD Mac. Collects everything git does not carry into one transfer folder:
#   DEST/agri-video-data.tar   episode audio/images/renders, cast candidates, bake-off runs, samples (~4 GB)
#   DEST/hf-hub/               the production model weights from ~/.cache/huggingface/hub (~45 GB)
#   DEST/claude-memory/        Claude Code's memory for this project
# Copy DEST to the new Mac (external SSD is fastest), then run there:
#   ./scripts/setup.sh --from DEST
#
#   ./scripts/pack_for_new_mac.sh /Volumes/SSD/agri-video-transfer [--no-models] [--no-data] [--with-parler]
#
# Re-runnable: the model copy resumes (rsync), the tar is rebuilt each time. Secrets (HF token, .env) are
# NOT copied; log in again on the new Mac.

set -u -o pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-}"; [ -n "$DEST" ] || { sed -n '2,13p' "$0"; exit 1; }
shift
MODELS=1; DATA=1; PARLER=0
for a in "$@"; do case "$a" in
  --no-models) MODELS=0 ;; --no-data) DATA=0 ;; --with-parler) PARLER=1 ;;
  *) echo "unknown option: $a"; exit 1 ;; esac; done
mkdir -p "$DEST" || exit 1
cd "$REPO" || exit 1

if [ "$DATA" = 1 ]; then
  echo "== media → $DEST/agri-video-data.tar"
  LIST="$(mktemp)"
  # gitignored files worth keeping (not envs, node_modules or downloadable models)
  for p in episodes/*/audio episodes/*/images episodes/*/render episodes/*/review/*.png \
           assets/cast/*/candidates assets/broll/clips assets/music \
           bakeoff/runs bakeoff/logs bakeoff/blind bakeoff/crops samples dashboard/runs remotion/public/episodes; do
    [ -e "$p" ] && echo "$p"
  done > "$LIST"
  tar -cf "$DEST/agri-video-data.tar.part" --exclude .DS_Store -T "$LIST" \
    && mv "$DEST/agri-video-data.tar.part" "$DEST/agri-video-data.tar" || { echo "tar failed"; exit 1; }
  rm -f "$LIST"
  echo "   $(du -h "$DEST/agri-video-data.tar" | cut -f1)"
fi

if [ "$MODELS" = 1 ]; then
  echo "== models → $DEST/hf-hub/ (resumable)"
  HUB="$HOME/.cache/huggingface/hub"
  REPOS="maya-research/maya2-native maya-research/Veena hubertsiuzdak/snac_24khz mlx-community/whisper-large-v3-turbo
         mlx-community/Ministral-3-14B-Instruct-2512-4bit black-forest-labs/flux-3-image-klein"
  [ "$PARLER" = 1 ] && REPOS="$REPOS ai4bharat/indic-parler-tts"
  mkdir -p "$DEST/hf-hub"
  for r in $REPOS; do
    d="models--$(echo "$r" | sed 's|/|--|g')"
    if [ -d "$HUB/$d" ]; then
      echo "   $r"
      # -a keeps the cache's relative symlinks (snapshots → blobs inside the same folder)
      rsync -a --partial "$HUB/$d" "$DEST/hf-hub/" || { echo "rsync failed for $r"; exit 1; }
    else
      echo "   $r not in cache, skipped (setup.sh will download it)"
    fi
  done
  echo "   $(du -sh "$DEST/hf-hub" | cut -f1)"
fi

MEM="$HOME/.claude/projects/$(printf '%s' "$REPO" | sed 's/[^A-Za-z0-9]/-/g')/memory"
if [ -d "$MEM" ]; then
  echo "== Claude memory → $DEST/claude-memory/"
  rsync -a "$MEM/" "$DEST/claude-memory/"
fi

echo
echo "Done. Uncommitted git changes are NOT in this folder; commit and push them first:"
git -C "$REPO" status --short | head -10
echo "On the new Mac: git clone <repo> ~/projects/agri-video && cd ~/projects/agri-video && ./scripts/setup.sh --from <this folder>"
