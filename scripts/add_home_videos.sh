#!/usr/bin/env bash
# Compress the three home-screen videos for the web and publish them on the hosted game.
#
#   bash scripts/add_home_videos.sh EARTH_VIDEO MOON_VIDEO MARS_VIDEO [--no-push]
#
# Each video becomes frontend/game/media/home/{earth,moon,mars}.mp4: 720p, 25 s, no sound,
# H.264 with fast start (plays while downloading). Usually 3-8 MB each, far under GitHub's
# 100 MB limit, so the website stays quick to open. Needs ffmpeg:
#   Ubuntu/Debian: sudo apt install ffmpeg      Fedora: sudo dnf install ffmpeg-free (or ffmpeg)
# Uses libx264 when available, else OpenH264 (Fedora's ffmpeg-free), else AV1: all play in browsers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/frontend/game/media/home"
[[ $# -ge 3 ]] || { sed -n 2,8p "$0"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is missing (Fedora: sudo dnf install -y ffmpeg-free, Ubuntu: sudo apt install -y ffmpeg)"; exit 1; }
encoders="$(ffmpeg -hide_banner -encoders 2>/dev/null)"
if grep -q " libx264 " <<<"$encoders"; then
  VCODEC=(-c:v libx264 -preset slow -crf 30 -profile:v high)
elif grep -q " libopenh264 " <<<"$encoders"; then
  VCODEC=(-c:v libopenh264 -b:v 1800k -profile:v high)
elif grep -q " libsvtav1 " <<<"$encoders"; then
  VCODEC=(-c:v libsvtav1 -crf 40 -preset 8)
else
  echo "This ffmpeg has no H.264 or AV1 encoder. Fedora: sudo dnf install -y ffmpeg-free openh264 (or ffmpeg from RPM Fusion)."; exit 1
fi
echo "Encoder: ${VCODEC[1]}"
mkdir -p "$OUT"
names=(earth moon mars)
for i in 0 1 2; do
  src="${@:$((i + 1)):1}"
  [[ -f "$src" ]] || { echo "Not found: $src"; exit 1; }
  dst="$OUT/${names[$i]}.mp4"
  echo ">> ${names[$i]}: $src"
  ffmpeg -hide_banner -loglevel error -y -ss 2 -i "$src" -t 25 \
    -vf "scale=-2:720:flags=lanczos,fps=30" "${VCODEC[@]}" \
    -pix_fmt yuv420p -an -movflags +faststart "$dst"
  size=$(du -m "$dst" | cut -f1)
  echo "   -> $dst (${size} MB)"
  if (( size > 90 )); then echo "Too big for GitHub; lower the quality (raise -crf)."; exit 1; fi
done
if [[ "${4:-}" == "--no-push" ]]; then echo "Done (not pushed)."; exit 0; fi
cd "$ROOT"
git add -f frontend/game/media/home/earth.mp4 frontend/game/media/home/moon.mp4 frontend/game/media/home/mars.mp4
git commit -m "Add home background videos (720p, compressed)"
git push origin "$(git branch --show-current)"
echo "Published. The website updates about a minute after the push."
