# AI Jukebox 🎵

An AI that writes, performs, and DJs your music. Generate a customizable song
(lyrics + music + cover art), then assemble a whole radio set where an
AI-generated DJ voices commentary between every track.

Everything runs against **class services only** — no paid APIs, no port 9000.

| Feature | Class service | Port | Used for |
|---|---|---|---|
| Text generation | Qwen3.6-35B-A3B | 9001 | lyrics, song captions, DJ scripts |
| Cover art | FLUX.2 klein 4B | 9006 | album artwork for every song |
| Music | ACE-Step 1.5 XL Turbo | 9007 | composing the actual songs |
| DJ speech | Chatterbox Multilingual V3 | 9008 | spoken commentary between tracks |

## Quick start

```bash
git clone <this-repo> && cd ai-jukebox

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then fill in your class endpoint URLs + API key
python scripts/smoke_test.py   # optional: verify all 4 services respond

uvicorn backend.app:app --reload
# open http://127.0.0.1:8000
```

## What you can do

- **Make a song** — pick genre, mood, theme, length, BPM, key, cover style;
  the app writes original lyrics, composes the music, and paints the cover.
- **Library** — every generation is stored locally (cover + audio + lyrics)
  and playable from the browser.
- **Make a show** — choose 2–5 tracks, a DJ personality, the DJ's language
  (23 languages/accent options: English, Spanish, French, German, Japanese…),
  and speech speed. The app generates the whole set plus AI-written, AI-spoken
  segues, then plays it end to end: opener → track → segue → track → …

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | class-service status dashboard |
| POST | `/api/songs` | generate one song (see body schema in `backend/app.py`) |
| GET | `/api/songs` / `/api/songs/{id}` | list / fetch songs |
| DELETE | `/api/songs/{id}` | remove a song |
| POST | `/api/shows` | generate a DJ'd collection (`n_tracks`, `dj_vibe`, …) |
| GET | `/api/shows` / `/api/shows/{id}` | list / fetch shows |
| GET | `/media/...` | generated audio / cover files |

## How a song is made

1. **Qwen** (9001) writes original lyrics, a production caption, and a cover
   prompt from your specs (single JSON call, server-side).
2. **ACE-Step** (9007) composes the track: `release_task` → poll
   `query_result` → download the finished MP3.
3. **FLUX** (9006) paints the cover from the prompt (steps 1 & 2 run in parallel).
4. Everything is saved under `storage/` and indexed in `storage/library.json`.
5. For a **show**, **Qwen** writes an opener + segues referencing each real
   track, and **Chatterbox** (9008) voices them between the songs.

## Safeguards (per assignment spec)

- Credentials live **server-side only**: `JUKEBOX_API_KEY` comes from `.env`
  (gitignored). Configuration examples use placeholders only
  (`.env.example`, `class-endpoints.txt.example`).
- No user uploads or voice recordings are accepted or stored by the app.
- No third-party music, lyrics, cover art, or voice samples are bundled —
  everything is generated on demand by the class services.
- Port 9000 is never used for app requests. No paid services anywhere.

## Project layout

```
backend/
  config.py     env-driven endpoints, key, storage
  services.py   HTTP clients for the four class services
  prompts.py    songwriter & DJ prompt templates
  generator.py  song + show pipelines
  store.py      local library persistence (storage/ is gitignored)
  app.py        FastAPI app & routes
static/         browser UI (vanilla JS player + jukebox controls)
scripts/
  smoke_test.py end-to-end class-service check
```
