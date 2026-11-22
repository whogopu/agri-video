#!/bin/zsh
# Download bake-off models one by one (priority order); while the next downloads, smoke-test the
# previous one on B01. Smoke runs never overlap (each waits for the previous); bakeoff run also waits
# for any other heavy job on the Mac.
cd "$(dirname "$0")/.."
caffeinate -i -s -w $$ &   # no idle sleep while downloading / testing
export HF_HUB_DISABLE_XET=${HF_HUB_DISABLE_XET:-0}   # xet is ~10x faster on a healthy line; set 1 if it stalls
smoke_pid=""
for m in "$@"; do
  echo "$(date +%H:%M) download $m" >> bakeoff/logs/fetch.log
  until uv run python -m pipeline.bakeoff download --model "$m" >> bakeoff/logs/download.log 2>&1; do
    echo "$(date +%H:%M) retry $m" >> bakeoff/logs/fetch.log; sleep 60
  done
  echo "$(date +%H:%M) downloaded $m" >> bakeoff/logs/fetch.log
  [[ -n $smoke_pid ]] && wait $smoke_pid
  uv run python -m pipeline.bakeoff run --shots B01 --model "$m" >> bakeoff/logs/smoke-B01.log 2>&1 &
  smoke_pid=$!
done
[[ -n $smoke_pid ]] && wait $smoke_pid
echo "$(date +%H:%M) all done" >> bakeoff/logs/fetch.log
