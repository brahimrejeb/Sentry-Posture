<div align="center">
  <img src="assets/sentry_logo.png" alt="Sentry" width="120" />
  <h1>Sentry</h1>
  <p><strong>Local, privacy-first posture monitor.</strong></p>
</div>

Sentry watches your craniovertebral angle (CVA) through your webcam and
nudges you when your head drifts forward. Frames are processed on your own
machine with [MediaPipe Pose Landmarker]; nothing is sent over the network.

## Quickstart

You need **Python 3.10–3.12**. That's it.

```bash
git clone https://github.com/<owner>/sentry.git
cd sentry
python run.py
```

`run.py` will, on first run:

1. Install [`uv`](https://github.com/astral-sh/uv) if it isn't already.
2. Create `.venv/` and install Python dependencies.
3. Download the default MediaPipe pose-landmarker model (~9 MB) into
   `~/.sentry/models/`.
4. Build the UI (or use the pre-built bundle from a release zip).
5. Open the dashboard at `http://127.0.0.1:47821` and dock an icon in your
   system tray. (We use 47821 instead of 8000/8080 to avoid colliding with
   the dev server you're probably already running. If 47821 is busy too,
   Sentry scans upward for the next free port and prints the URL.)

Re-running `python run.py` is fast — the launcher only does the work that's
actually missing.

### Daily use

Once setup has succeeded once, you have two options:

- **Foreground** (dev / debugging): `python run.py` — output streams in
  the terminal, Ctrl+C stops it.
- **Background** (recommended): `start.bat` on Windows / `./start.sh` on
  macOS/Linux — Sentry boots into the tray and the terminal returns
  immediately. Closing the terminal does **not** kill the app. Quit it
  from the tray icon.

If you'd rather have Sentry come up automatically every time you log in,
flip on Settings → Startup → "Start Sentry automatically when I log in".
The boot log lives at `~/.sentry/sentry.log` if you ever need to debug it.

## Modes

Sentry ships in two flavours, switchable any time from Settings:

- **Simple** (default) — slouch detection and alerts. One-screen UI:
  Live + Settings.
- **Advanced** — adds posture history (Today / Week / Month / Year),
  daily goals + streaks, stand-up reminders, and a debug-overlay video
  preview.

Switching to Advanced begins recording history from that moment on.
Switching back stops new recording but leaves your existing data on
disk so you can flip back later.

## Auto-start

Settings → Startup has a one-toggle "Start Sentry automatically when I
log in". It registers a per-user entry on your platform — no admin
password needed:

| OS      | Where it's written                                                                  |
| ------- | ----------------------------------------------------------------------------------- |
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Sentry`                         |
| macOS   | `~/Library/LaunchAgents/com.sentry.posture.plist`                                   |
| Linux   | `~/.config/autostart/sentry.desktop`                                                |

Sentry boots quietly to the system tray on login. Click the tray icon
to open the dashboard.

## How it works

- **Calibrate** once by sitting upright and pressing _Calibrate_. Sentry
  averages your CVA over 30 frames so the baseline is stable.
- A small **state machine** decides whether you're being tracked (`locked`),
  searching for you (`searching`), away from your desk (`paused`), or off
  (`idle`).
- When you return after a break, Sentry enters a 5-second **settling
  window** before alerts can fire — so you don't get scolded the moment you
  sit back down.
- If multiple people are in frame, Sentry locks onto the person whose body
  proportions match the one you calibrated against and ignores the rest.
- Smoothing: a 1-second rolling median of the CVA stream eliminates jitter,
  and an alert only fires when at least 70 % of frames in the configured
  window are below threshold.

See [`docs/architecture.md`](docs/architecture.md) for the system diagram
and [`docs/clinical_research.md`](docs/clinical_research.md) for the
research that informs the defaults.

## Privacy

- All inference runs locally on CPU.
- No frames, telemetry, or identifiers are uploaded.
- The video preview in _Diagnostics_ exists only inside the FastAPI process
  and is served to `127.0.0.1`.

## Configuration

Settings live in `~/.sentry/config.json` and are also editable from the UI:

| Setting                    | What it does                                        |
| -------------------------- | --------------------------------------------------- |
| Tracking model             | `lite` / `full` / `heavy` — accuracy vs CPU cost    |
| Sensitivity threshold      | How many degrees of CVA drop count as slouching     |
| Slouch time window         | How long bad posture must persist before an alert  |
| Alert cooldown             | Quiet period after an alert                        |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Run `python run.py --dev` for the
hot-reloading contributor experience.

## License

[GPL-3.0-or-later](LICENSE).

[MediaPipe Pose Landmarker]: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
