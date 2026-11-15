# Home-screen background videos

Put one video per mission here, with exactly these names:

| File | Shown when this mission is selected |
| --- | --- |
| `earth.mp4` | Earth Observation (default) |
| `moon.mp4` | Lunar Exploration |
| `mars.mp4` | Mars Exploration |

They play muted and looped behind the home screen. If a file is missing, the drawn planet
shows instead, so the game still works without them.

Keep them small: GitHub refuses files over 100 MB, and a big video slows the home screen.
To compress one (1080p, no sound, usually 10-30 MB):

```bash
ffmpeg -i input.mp4 -vf "scale=-2:1080" -c:v libx264 -preset veryfast -crf 28 -an -movflags +faststart earth.mp4
```

`*.mp4` in this folder is git-ignored so a 900 MB file is never pushed by accident.
To commit compressed videos on purpose: `git add -f frontend/game/media/home/earth.mp4`.
