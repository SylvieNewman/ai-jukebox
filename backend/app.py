"""AI Jukebox - FastAPI application.

Serves the static frontend and a small REST API. All calls to the class
services happen server-side; the browser never sees credentials.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
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
    dj_language: str = Field(
        "en",
        description="DJ language/accent (Chatterbox language code, e.g. en, es, fr, de, ja, ko, zh…)",
    )
    dj_speed: Optional[float] = Field(
        None, ge=0.5, le=1.5,
        description="DJ speech speed; None = relaxed default (0.9x)",
    )
    artist: str = ""


class PlaylistCreate(BaseModel):
    name: str
    public: bool = True


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    public: Optional[bool] = None


class PlaylistItemAdd(BaseModel):
    kind: str  # "song" | "show"
    id: str


class PlaylistItemVisibility(BaseModel):
    public: bool


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
            cover_style=req.cover_style, dj_vibe=req.dj_vibe,
            dj_language=req.dj_language, dj_speed=req.dj_speed,
            artist_hint=req.artist,
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


# ------------------------------------------------------------ playlists --
# Lightweight collaboration: visitors pick a nickname (sent as X-Username),
# playlists are attributed to it, and each playlist (plus every item inside)
# carries a public/private flag. This is trust-based, not real authentication.

def _now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _user(request: Request) -> str:
    """The visitor's nickname, or '' when unset."""
    return (request.headers.get("x-username") or "").strip()


def _resolve_item(item: dict) -> Optional[dict]:
    """Attach the referenced song/show details (None once the media is gone)."""
    if item.get("kind") == "song":
        s = store.get_song(item["id"])
        return None if not s else {
            "title": s.get("title", "Untitled"),
            "artist": s.get("artist", ""),
            "cover_url": s.get("cover_url"),
            "audio_url": s.get("audio_url"),
            "lyrics": s.get("lyrics") or "",
            "duration": s.get("duration"),
            "genre": s.get("genre"),
            "mood": s.get("mood"),
            "language": s.get("language"),
        }
    sh = store.get_show(item["id"])
    return None if not sh else {
        "name": sh.get("name", "Show"),
        "segments": len(sh.get("segments", [])),
    }


def _playlist_summary(pl: dict) -> dict:
    cover = ""
    for it in pl.get("items", []):
        if it.get("kind") != "song":
            continue
        s = store.get_song(it["id"])
        if s and s.get("cover_url"):
            cover = s["cover_url"]
            break
    return {
        "id": pl["id"],
        "name": pl["name"],
        "owner": pl["owner"],
        "public": bool(pl.get("public", True)),
        "created": pl.get("created", ""),
        "item_count": len(pl.get("items", [])),
        "cover_url": cover,
    }


@app.get("/api/playlists")
def api_list_playlists(request: Request, owner: str = "") -> dict:
    """Browse: with ?owner=NAME -> that person's playlists (private ones only
    for the owner themself); without -> every public playlist (the community)."""
    me = _user(request)
    out = []
    for pl in store.list_playlists():
        if owner and pl["owner"] != owner:
            continue
        is_mine = pl["owner"] == me
        if not is_mine and not pl.get("public", True):
            continue
        out.append(_playlist_summary(pl))
    return {"playlists": out}


@app.get("/api/playlists/{playlist_id}")
def api_get_playlist(playlist_id: str, request: Request) -> dict:
    pl = store.get_playlist(playlist_id)
    me = _user(request)
    if not pl or (not pl.get("public", True) and pl["owner"] != me):
        raise HTTPException(status_code=404, detail="playlist not found")
    is_owner = pl["owner"] == me
    items = []
    for it in pl.get("items", []):
        if not is_owner and not it.get("public", pl.get("public", True)):
            continue  # hide other people's private items
        items.append({
            "uid": it.get("uid", ""),
            "kind": it.get("kind", "song"),
            "id": it.get("id", ""),
            "public": bool(it.get("public", pl.get("public", True))),
            "ref": _resolve_item(it),
        })
    return {
        "id": pl["id"], "name": pl["name"], "owner": pl["owner"],
        "public": bool(pl.get("public", True)), "created": pl.get("created", ""),
        "is_owner": is_owner, "items": items,
    }


@app.post("/api/playlists")
def api_create_playlist(req: PlaylistCreate, request: Request) -> dict:
    me = _user(request)
    if not me:
        raise HTTPException(status_code=400, detail="set a nickname before creating a playlist")
    name = (req.name or "").strip()
    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="playlist name must be 1-40 characters")
    return store.save_playlist({
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "owner": me,
        "public": bool(req.public),
        "created": _now(),
        "items": [],
    })


@app.patch("/api/playlists/{playlist_id}")
def api_update_playlist(playlist_id: str, req: PlaylistUpdate, request: Request) -> dict:
    pl = store.get_playlist(playlist_id)
    me = _user(request)
    if not pl:
        raise HTTPException(status_code=404, detail="playlist not found")
    if pl["owner"] != me:
        raise HTTPException(status_code=403, detail="only the owner can edit this playlist")
    if req.name is not None:
        name = req.name.strip()
        if not name or len(name) > 40:
            raise HTTPException(status_code=400, detail="playlist name must be 1-40 characters")
        pl["name"] = name
    if req.public is not None:
        pl["public"] = bool(req.public)
    return store.save_playlist(pl)


@app.delete("/api/playlists/{playlist_id}")
def api_delete_playlist(playlist_id: str, request: Request) -> dict:
    pl = store.get_playlist(playlist_id)
    me = _user(request)
    if not pl:
        raise HTTPException(status_code=404, detail="playlist not found")
    if pl["owner"] != me:
        raise HTTPException(status_code=403, detail="only the owner can delete this playlist")
    store.delete_playlist(playlist_id)
    return {"deleted": playlist_id}


@app.post("/api/playlists/{playlist_id}/items")
def api_add_playlist_item(playlist_id: str, req: PlaylistItemAdd, request: Request) -> dict:
    pl = store.get_playlist(playlist_id)
    me = _user(request)
    if not pl:
        raise HTTPException(status_code=404, detail="playlist not found")
    if pl["owner"] != me:
        raise HTTPException(status_code=403, detail="only the owner can edit this playlist")
    if req.kind not in ("song", "show"):
        raise HTTPException(status_code=400, detail="item kind must be 'song' or 'show'")
    exists = store.get_song(req.id) if req.kind == "song" else store.get_show(req.id)
    if not exists:
        raise HTTPException(status_code=400, detail=f"no such {req.kind} in the library")
    if any(it["kind"] == req.kind and it["id"] == req.id for it in pl.get("items", [])):
        raise HTTPException(status_code=400, detail="already in this playlist")
    pl.setdefault("items", []).append({
        "uid": uuid.uuid4().hex[:8],
        "kind": req.kind,
        "id": req.id,
        "public": bool(pl.get("public", True)),  # inherit the playlist default
    })
    return store.save_playlist(pl)


@app.patch("/api/playlists/{playlist_id}/items/{uid}")
def api_set_item_visibility(playlist_id: str, uid: str, req: PlaylistItemVisibility,
                            request: Request) -> dict:
    pl = store.get_playlist(playlist_id)
    me = _user(request)
    if not pl:
        raise HTTPException(status_code=404, detail="playlist not found")
    if pl["owner"] != me:
        raise HTTPException(status_code=403, detail="only the owner can edit this playlist")
    for it in pl.get("items", []):
        if it.get("uid") == uid:
            it["public"] = bool(req.public)
            return store.save_playlist(pl)
    raise HTTPException(status_code=404, detail="item not found")


@app.delete("/api/playlists/{playlist_id}/items/{uid}")
def api_remove_playlist_item(playlist_id: str, uid: str, request: Request) -> dict:
    pl = store.get_playlist(playlist_id)
    me = _user(request)
    if not pl:
        raise HTTPException(status_code=404, detail="playlist not found")
    if pl["owner"] != me:
        raise HTTPException(status_code=403, detail="only the owner can edit this playlist")
    before = len(pl.get("items", []))
    pl["items"] = [it for it in pl.get("items", []) if it.get("uid") != uid]
    if len(pl["items"]) == before:
        raise HTTPException(status_code=404, detail="item not found")
    return store.save_playlist(pl)


# ------------------------------------------------------------ frontend -----
app.mount("/", StaticFiles(directory=str(config.PROJECT_ROOT / "static"), html=True), name="static")


@app.exception_handler(services.ServiceError)
def _service_error_handler(_, exc: services.ServiceError):
    return JSONResponse(status_code=502, content={"error": str(exc)})
