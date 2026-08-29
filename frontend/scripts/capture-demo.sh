#!/usr/bin/env bash
#
# Record the demo at 60fps by capturing the screen, instead of using
# Playwright's own recorder.
#
# Why: Playwright's video is hard-capped at 25fps and draws no mouse cursor.
# Measured on this project — a 370-second run produced exactly 9,256 frames, and
# every click in it appeared to happen by itself. This captures the real window
# at 60fps and crops to the page, so the eased cursor movement and the smooth
# scrolling in tests/e2e/lib/cinematics.ts survive to the finished file.
#
# ONE-TIME SETUP. macOS will not let any process capture the screen until you
# allow it, per-application:
#
#   System Settings → Privacy & Security → Screen & System Audio Recording
#   → add (and tick) the terminal you run this from — Terminal, iTerm, or the
#     editor whose integrated terminal you are using.
#
# Then quit and reopen that terminal. Without this, ffmpeg hangs forever on the
# capture device with no error, which is exactly as much fun as it sounds.
#
# Usage, from the frontend directory:
#
#   bash scripts/capture-demo.sh
#
# Leave the machine alone while it runs — it is filming your actual screen, so
# anything you do lands in the video. Roughly six and a half minutes.

set -euo pipefail

cd "$(dirname "$0")/.."

OUT_DIR="tests/e2e/recordings"
RAW="$OUT_DIR/capture-raw.mkv"
FINAL="../docs/demo-recording.mp4"
RECT="$OUT_DIR/viewport.json"
SCREEN_INDEX="${SCREEN_INDEX:-3}"

mkdir -p "$OUT_DIR"
rm -f "$RAW" "$RECT"

command -v ffmpeg >/dev/null || { echo "ffmpeg not found: brew install ffmpeg"; exit 1; }

echo "Checking screen-recording permission…"
if ! timeout 12 ffmpeg -loglevel error -f avfoundation -framerate 30 \
      -i "${SCREEN_INDEX}:none" -t 1 -f null - 2>/dev/null; then
  cat <<'MSG'

Cannot capture the screen. Two likely reasons:

  1. Permission. System Settings → Privacy & Security → Screen & System Audio
     Recording → allow your terminal, then restart the terminal.

  2. Wrong device index. Run:
         ffmpeg -f avfoundation -list_devices true -i ""
     find the "Capture screen 0" line, and re-run with:
         SCREEN_INDEX=<n> bash scripts/capture-demo.sh

MSG
  exit 1
fi
echo "  ok"

# Raw capture into mkv rather than mp4: an interrupted mp4 has no moov atom and
# is unplayable, while mkv stays readable however it ends.
echo "Recording the screen at 60fps…"
ffmpeg -loglevel error -f avfoundation -capture_cursor 0 -framerate 60 \
  -i "${SCREEN_INDEX}:none" -c:v libx264 -preset ultrafast -crf 16 \
  -pix_fmt yuv420p -y "$RAW" &
FFMPEG_PID=$!
# Killed on any exit path, so a failed run does not leave a recorder running.
trap 'kill -INT "$FFMPEG_PID" 2>/dev/null || true; wait "$FFMPEG_PID" 2>/dev/null || true' EXIT

sleep 2

echo "Running the demo…"
set +e
npx playwright test --project=demo
TEST_STATUS=$?
set -e

sleep 1
kill -INT "$FFMPEG_PID" 2>/dev/null || true
wait "$FFMPEG_PID" 2>/dev/null || true
trap - EXIT

[ -s "$RAW" ] || { echo "No capture was written."; exit 1; }

if [ ! -f "$RECT" ]; then
  echo "The run did not report a viewport rectangle; leaving the capture uncropped:"
  echo "  $RAW"
  exit "$TEST_STATUS"
fi

# Crop to the page, in physical pixels. Even values only — libx264 with yuv420p
# needs both dimensions divisible by two.
read -r CX CY CW CH < <(python3 - "$RECT" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
d = r["dpr"]
vals = [r["x"] * d, r["y"] * d, r["width"] * d, r["height"] * d]
print(" ".join(str(int(v) // 2 * 2) for v in vals))
PY
)

echo "Cropping to ${CW}x${CH} at ${CX},${CY} and encoding…"
ffmpeg -loglevel error -i "$RAW" \
  -vf "crop=${CW}:${CH}:${CX}:${CY},scale=1440:900:flags=lanczos" \
  -r 60 -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  -movflags +faststart -an -y "$FINAL"

echo
echo "Done: $(cd .. && pwd)/docs/demo-recording.mp4"
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,avg_frame_rate \
  -show_entries format=duration,size -of default=nw=1 "$FINAL"
echo
echo "Raw uncropped capture kept at $RAW — delete it when you are happy."
exit "$TEST_STATUS"
