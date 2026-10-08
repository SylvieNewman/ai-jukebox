"""AI Jukebox - FastAPI application.

Serves the static frontend and a small REST API. All calls to the class
services happen server-side; the browser never sees credentials.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, generator, services, store, suggestion_pool

config.validate()  # fail fast with a clear message when .env is not configured

app = FastAPI(title="AI Jukebox", version="1.0.0")

# Instant "random X" rolls: warm pools keep fresh AI ideas ready so the dice
# buttons never block on the text model's generation time.
THEME_POOL = suggestion_pool.SuggestionPool(
    suggestion_pool.ask_theme, suggestion_pool.THEME_FALLBACKS
)
NAME_POOL = suggestion_pool.SuggestionPool(
    suggestion_pool.ask_name_pair, suggestion_pool.NAME_FALLBACKS
)


# ------------------------------------------------------------------ models --
class SongRequest(BaseModel):
    genre: str = Field("pop", description="e.g. pop, rock, hip-hop, electronic, jazz")
    mood: str = Field("upbeat", description="emotional vibe of the track")
    theme: str = Field("driving at night", description="what the song is about")
    duration: float = Field(25.0, ge=8, le=120, description="song length in seconds (8s to 2 minutes)")
    vocals: bool = True
    language: str = Field("English", description="language for the lyrics and vocals")
    bpm: Optional[int] = Field(None, ge=60, le=200)
    key_scale: str = "C major"
    cover_style: str = "vibrant album art"
    artist: str = ""
    title: str = ""
    seed: Optional[int] = None


class ShowRequest(BaseModel):
    n_tracks: int = Field(3, ge=1, le=6)
    genre: str = "pop"
    mood: str = "upbeat"
    theme: str = "driving at night"
    duration: float = Field(25.0, ge=8, le=120, description="song length in seconds (8s to 2 minutes)")
    vocals: bool = True
    language: str = "English"
    bpm: Optional[int] = None
    key_scale: str = "C major"
    cover_style: str = "vibrant album art"
    dj_vibe: str = Field("chill and smooth", description="DJ personality")
    artist: str = ""


# ------------------------------------------------------------------- api ---
@app.get("/api/health")
def api_health() -> dict:
    statuses = store.health_check()
    ok = all(v == "ok" for v in statuses.values())
    return {"status": "ok" if ok else "degraded", "services": statuses,
            "key_configured": bool(config.API_KEY)}


@app.get("/api/themes/random")
def api_random_theme() -> dict:
    """Roll a fresh song theme, served instantly from the warm AI theme pool."""
    return {"theme": THEME_POOL.next()}


@app.get("/api/names/random")
def api_random_names() -> dict:
    """Roll a fresh (artist, title) pair, served instantly from the warm pool."""
    artist, title = NAME_POOL.next()
    return {"artist": artist, "title": title}


@app.post("/api/songs")
def api_create_song(req: SongRequest) -> dict:
    try:
        return generator.generate_song(
            genre=req.genre, mood=req.mood, theme=req.theme,
            duration=req.duration, vocals=req.vocals, language=req.language,
            bpm=req.bpm, key_scale=req.key_scale, cover_style=req.cover_style,
            artist_hint=req.artist, title_hint=req.title, seed=req.seed,
        )
    except services.ServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/songs")
def api_list_songs() -> dict:
    return {"songs": store.list_songs()}


@app.get("/api/songs/{song_id}")
def api_get_song(song_id: str) -> dict:
    song = store.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="song not found")
    return song


@app.delete("/api/songs/{song_id}")
def api_delete_song(song_id: str) -> dict:
    if not store.delete_song(song_id):
        raise HTTPException(status_code=404, detail="song not found")
    return {"deleted": song_id}


@app.post("/api/shows")
def api_create_show(req: ShowRequest) -> dict:
    try:
        return generator.generate_show(
            n_tracks=req.n_tracks, genre=req.genre, mood=req.mood,
            theme=req.theme, duration=req.duration, vocals=req.vocals,
            language=req.language, bpm=req.bpm, key_scale=req.key_scale,
            cover_style=req.cover_style, dj_vibe=req.dj_vibe, artist_hint=req.artist,
        )
    except services.ServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/shows")
def api_list_shows() -> dict:
    return {"shows": store.list_shows()}


@app.get("/api/shows/{show_id}")
def api_get_show(show_id: str) -> dict:
    show = store.get_show(show_id)
    if not show:
        raise HTTPException(status_code=404, detail="show not found")
    return show


@app.delete("/api/shows/{show_id}")
def api_delete_show(show_id: str) -> dict:
    if not store.delete_show(show_id):
        raise HTTPException(status_code=404, detail="show not found")
    return {"deleted": show_id}


# --------------------------------------------------------------- media -----
@app.get("/media/songs/{song_id}/{file_name}")
def media_song(song_id: str, file_name: str) -> FileResponse:
    path = store.song_file(song_id, file_name)
    if not path:
        raise HTTPException(status_code=404, detail="media not found")
    return FileResponse(str(path))


@app.get("/media/shows/{show_id}/{file_name}")
def media_show(show_id: str, file_name: str) -> FileResponse:
    path = store.show_voice_file(show_id, file_name)
    if not path:
        raise HTTPException(status_code=404, detail="media not found")
    return FileResponse(str(path))


# ------------------------------------------------------------ frontend -----
app.mount("/", StaticFiles(directory=str(config.PROJECT_ROOT / "static"), html=True), name="static")


@app.exception_handler(services.ServiceError)
def _service_error_handler(_, exc: services.ServiceError):
    return JSONResponse(status_code=502, content={"error": str(exc)})
