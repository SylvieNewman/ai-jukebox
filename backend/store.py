"""Local library persistence. Generated media lives under storage/ (gitignored);
metadata is a small JSON index. No user content ever leaves the machine."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from . import config


def _read_index(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_index(path: Path, index: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2), "utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ songs --
def new_song_dir() -> Path:
    d = config.STORAGE_DIR / "songs" / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_song(song: dict) -> dict:
    index = _read_index(config.LIBRARY_FILE)
    index.setdefault("songs", {})
    index["songs"][song["id"]] = song
    _write_index(config.LIBRARY_FILE, index)
    return song


def list_songs() -> list[dict]:
    return sorted(_read_index(config.LIBRARY_FILE).get("songs", {}).values(),
                  key=lambda s: s.get("created", ""), reverse=True)


def get_song(song_id: str) -> Optional[dict]:
    return _read_index(config.LIBRARY_FILE).get("songs", {}).get(song_id)


def delete_song(song_id: str) -> bool:
    index = _read_index(config.LIBRARY_FILE)
    songs = index.get("songs", {})
    if song_id not in songs:
        return False
    del songs[song_id]
    _write_index(config.LIBRARY_FILE, index)
    shutil.rmtree(config.STORAGE_DIR / "songs" / song_id, ignore_errors=True)
    return True


def song_file(song_id: str, name: str) -> Optional[Path]:
    path = (config.STORAGE_DIR / "songs" / song_id / name).resolve()
    root = (config.STORAGE_DIR / "songs").resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


# ------------------------------------------------------------------ shows --
def save_show(show: dict) -> dict:
    index = _read_index(config.SHOWS_FILE)
    index.setdefault("shows", {})
    index["shows"][show["id"]] = show
    _write_index(config.SHOWS_FILE, index)
    return show


def list_shows() -> list[dict]:
    return sorted(_read_index(config.SHOWS_FILE).get("shows", {}).values(),
                  key=lambda s: s.get("created", ""), reverse=True)


def get_show(show_id: str) -> Optional[dict]:
    return _read_index(config.SHOWS_FILE).get("shows", {}).get(show_id)


def delete_show(show_id: str) -> bool:
    index = _read_index(config.SHOWS_FILE)
    shows = index.get("shows", {})
    if show_id not in shows:
        return False
    del shows[show_id]
    _write_index(config.SHOWS_FILE, index)
    shutil.rmtree(config.STORAGE_DIR / "shows" / show_id, ignore_errors=True)
    return True


def show_voice_file(show_id: str, name: str) -> Optional[Path]:
    path = (config.STORAGE_DIR / "shows" / show_id / name).resolve()
    root = (config.STORAGE_DIR / "shows").resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def health_check() -> dict:
    """Lightweight reachability check for every class service (used by /api/health)."""
    from . import services

    result = {}
    probes = {
        "text (9001)": (config.TEXT_URL, "/v1/models"),
        "image (9006)": (config.IMAGE_URL, "/v1/models"),
        "music (9007)": (config.MUSIC_URL, "/health"),
        "voice (9008)": (config.VOICE_URL, "/info"),
    }
    for label, (base, path) in probes.items():
        try:
            status, _ = services._call(base, path, method="GET", timeout=6)
            result[label] = "ok" if status == 200 else f"HTTP {status}"
        except Exception as exc:  # noqa: BLE001
            result[label] = f"error: {exc}"
    return result
