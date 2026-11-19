#!/usr/bin/env bash
# Placeholder assets for the phase 2 test composition (not real content).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=public/test
mkdir -p public/brand && cp ../assets/brand/logo.png public/brand/logo.png
mkdir -p "$OUT/audio" "$OUT/images" "$OUT/broll"
# Dummy narration: quiet tones, one per scene, with the durations used in src/test/testEpisode.ts
i=0
for spec in "3.2:330" "4.5:392" "4.3:440" "4.5:494" "3.5:523"; do
  i=$((i+1)); dur=${spec%%:*}; f=${spec##*:}
  ffmpeg -v error -y -f lavfi -i "sine=frequency=$f:duration=$dur:sample_rate=48000" -af "volume=0.08" -ac 1 "$OUT/audio/scene-0$i.wav"
done
# Placeholder still at the mflux output size (1344x768) with a grid so pan/zoom is visible
ffmpeg -v error -y -f lavfi -i "mandelbrot=s=1344x768:end_pts=1" -vf "drawgrid=w=96:h=96:t=2:c=white@0.4" -frames:v 1 "$OUT/images/scene-02.png"
ffmpeg -v error -y -f lavfi -i "mandelbrot=s=768x1344:end_pts=1" -vf "drawgrid=w=96:h=96:t=2:c=white@0.4" -frames:v 1 "$OUT/images/scene-02-portrait.png"
# Placeholder B-roll clip: 8 s, 1080p30, H.264
ffmpeg -v error -y -f lavfi -i "testsrc2=s=1920x1080:r=30:d=8" -c:v libx264 -pix_fmt yuv420p -crf 23 "$OUT/broll/test-clip.mp4"
echo "test assets written to $OUT"
