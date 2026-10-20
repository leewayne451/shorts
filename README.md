# whatif-shorts

Automatically generates a ~30-second vertical (1080×1920, 30 fps) **"What if [X] vanished?"** short video every day. A hidden narrator asks the question, then walks through the consequences hour-by-hour and day-by-day while on-screen cartoon characters act out what happens.

Runs entirely on GitHub Actions. Requires a **free Groq API key**, a **free Pixabay API key**, and (optionally) a **Telegram bot** to receive the video for human approval.

---

## What it does

1. Picks a subject from `subjects.txt` (whole classes of objects or animals — "bees", "all cars", "the moon").
2. Asks Groq (Llama 3.3 70B) to write an opening question ("What if bees vanished?") and 3–7 consequence beats labeled "+1 hour", "+1 day", "+1 week"…
3. Fact-checks each claim against Wikipedia; on fail, picks a new subject.
4. Narrates with edge-tts (voice `en-US-AvaNeural`, fallback espeak-ng).
5. Generates a procedural **mysterious** music bed (minor key, 60–80 BPM) and ducks it under the voice.
6. Fetches real photos from Pixabay and renders 1–5 flat-vector characters reacting to each beat.
7. Renders 900 frames with skia-python, pipes to ffmpeg, muxes audio, outputs a 30-second H.264 `final.mp4`.
8. QA checks duration, resolution, audio, mean volume, frame variety, and caption presence.
9. Sends the video to Telegram with a caption, then a second message with full captions, verdicts, sources, credits, and an AI-disclosure note.
10. Uploads the mp4 plus the full run folder as a GitHub Actions artifact (30 days).

---

## 10-step "upload and run"

1. **Fork or create a new empty GitHub repo** named `whatif-shorts`.
2. **Unzip the provided files into the repo root** (you should see `config.yaml`, `whatif/`, `.github/`, etc. at the top level).
3. `git add -A && git commit -m "init" && git push`.
4. **Get a free Groq key**: <https://console.groq.com/keys> → "Create key" → copy.
5. **Get a free Pixabay key**: <https://pixabay.com/api/docs/> → sign in → your key is on that page.
6. **Create a Telegram bot** (optional): talk to [@BotFather](https://t.me/botfather) → `/newbot` → copy the token. Send any message to your new bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat.id`.
7. In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add each of the four secrets (see table below).
8. Go to **Actions → generate → Run workflow**, leave fields blank, click "Run workflow".
9. Wait ~5–10 minutes. The run's "Summary" page links to the artifact (download `final.mp4`).
10. Once you're happy, the daily schedule (09:00 UTC) will keep generating a new video each day.

---

## Secrets

| Name | Required | What it does |
|---|---|---|
| `GROQ_API_KEY` | **required** | Calls Groq for the script and fact-check. |
| `PIXABAY_API_KEY` | **required** | Fetches stock photos. Missing → question_mark icon fallback (run still succeeds). |
| `TELEGRAM_BOT_TOKEN` | optional | Sends the video for approval. Missing → skips Telegram. |
| `TELEGRAM_CHAT_ID` | optional | Chat or group id to send to. Required if bot token is set. |

---

## Getting the free keys

- **Groq**: <https://console.groq.com/keys>. Free tier is generous; a typical run uses < 5,000 tokens.
- **Pixabay**: <https://pixabay.com/api/docs/>. Free tier: 100 requests / 60 s. Every downloaded photo is cached in `assets/photo_cache/` so repeat runs make no calls.
- **Telegram**: bot via @BotFather, chat id via `getUpdates` as described in the 10-step guide.

---

## Running locally

### macOS / Linux

```bash
# install system deps
brew install ffmpeg espeak-ng   # or: apt-get install ffmpeg espeak-ng

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="..."
export PIXABAY_API_KEY="..."
python -m whatif.run --subject "bees"
```

### Windows PowerShell

```powershell
# install system deps with winget
winget install ffmpeg
winget install eSpeak-NG.eSpeak-NG

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GROQ_API_KEY = "..."
$env:PIXABAY_API_KEY = "..."
python -m whatif.run --subject "bees"
```

`make` is optional and **not required on Windows** — run `python -m whatif.run` directly.

The output is `runs/<YYYYMMDD-HHMMSS>-what-if-<subject>-vanished/final.mp4`.

---

## Expected cost

**Zero** on the Groq free tier and Pixabay free tier. GitHub Actions free tier covers the scheduled runs (2,000 minutes/month on private repos, unlimited on public repos). A 30-second render takes ~3–5 minutes on a standard Ubuntu runner.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `edge-tts failed` and falls back to espeak-ng | Check network access to `speech.platform.bing.com` (edge-tts needs it). espeak-ng output is fine but robotic; that's the fallback. |
| `no word boundaries` in voice.json | edge-tts sometimes only emits sentence boundaries on some networks. The voice stage already expands them proportionally; captions still work. |
| `ffmpeg not found` | Install ffmpeg; on Ubuntu `sudo apt-get install ffmpeg`, on macOS `brew install ffmpeg`, on Windows `winget install ffmpeg`. |
| `font missing` | The workflow auto-downloads Poppins Bold. Locally, `assets/fonts/Poppins-Bold.ttf` must exist; otherwise DejaVu Sans Bold is used. |
| `Groq returned bad JSON` | Transient; the script stage retries up to 3 times with the validation error fed back. Check `runs/<id>/script.json` if it fails repeatedly. |
| `Pixabay rate limit` / `wrong photo` | The cache prevents repeat hits; a 429 triggers exponential backoff. Use more specific 2–4 word queries like "honey jar" instead of "honey". |
| `opening question rejected by schema` | Llama sometimes writes "What if bees were to vanish?"; the schema retries with the exact phrase as feedback. If it still fails 3×, try a simpler subject. |
| `render time over CI timeout` | 30 s renders are ~3–5 min on `ubuntu-latest`; if you raise duration, bump `timeout-minutes` in `generate.yml`. |

---

## How to extend

### Add a new hair style

1. In `whatif/render/hair_accessories.py`, add a function `_style_<name>(canvas, cfg, color, head_d)`.
2. Register it in `_HAIR_FN`.
3. Add `<name>` to `_HAIR_STYLES` and to `HAIR_STYLES` in `whatif/script_stage.py`.

### Add a new accessory

Same pattern: `_acc_<name>` → `_ACC_FN` → `_ACCESSORIES` in both files.

### Add a new hand

In `whatif/render/hands.py`, write `_hand_<name>(canvas, cfg, t)` using the shared helpers (`_palm`, `_finger_capsule`, `_thumb`, `_filled_blob`). Register in `_REGISTRY`.

### Add a new icon

In `whatif/render/props.py`, write `_draw_<name>(canvas, cfg, t)`. Register in `_REGISTRY` and add to `ICONS` in `whatif/script_stage.py`.

### Add a new scene template

1. In `whatif/render/scenes.py`, write `_render_<name>(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches)`.
2. Register in `_RENDERERS` and in `_TEMPLATES`.
3. Add the name to `SCENE_TEMPLATES` in `whatif/script_stage.py`.
4. Add a test in `tests/test_scenes.py`.

---

## Photo licensing

Photos are downloaded from Pixabay via the Pixabay API and cached locally. Per the **Pixabay Content License**, images are free to use, and we record the photographer's username and the photo page URL in `credits.json` for every run. Credits are also included in the Telegram follow-up message and the API requests are cached for 24 h to comply with Pixabay's terms. **Re-check the current license terms before commercial use.**

---

## AI disclosure

The narration is AI-generated (edge-tts or espeak-ng) and the visuals are programmatically drawn by skia. Platforms (including Telegram, YouTube, TikTok, and Instagram) increasingly require that synthetic media be disclosed — the Telegram follow-up message includes a "Voice and visuals are AI-generated." line by default.