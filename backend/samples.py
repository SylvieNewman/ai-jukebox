"""Bundled sample songs: seed a fresh library with three ready-to-play tracks.

The repo ships three short songs (audio + cover + metadata) under samples/,
generated in advance with the class endpoints (9001 / 9006 / 9007). On
startup the app copies them into storage/ and registers them in the library,
so a fresh clone has three playable songs immediately -- no generation call
is needed to hear them. Seeding is idempotent: sample ids already present in
the library are skipped.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil

from . import config, store


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _load_manifest() -> list[dict]:
    path = config.PROJECT_ROOT / "samples" / "manifest.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def seed_samples() -> int:
    """Copy any missing bundled samples into storage and index them.

    Returns the number of samples added (0 when already seeded).
    """
    added = 0
    for item in _load_manifest():
        sid = str(item.get("id") or "").strip()
        if not sid or store.get_song(sid):
            continue
        src = config.PROJECT_ROOT / "samples" / sid
        audio, cover = src / "audio.mp3", src / "cover.jpg"
        if not (audio.is_file() and cover.is_file()):
            continue
        dest = config.STORAGE_DIR / "songs" / sid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio, dest / "audio.mp3")
        shutil.copy2(cover, dest / "cover.jpg")

        song = dict(item)
        song["id"] = sid
        song["cover_url"] = f"/media/songs/{sid}/cover.jpg"
        song["audio_url"] = f"/media/songs/{sid}/audio.mp3"
        song["created"] = song.get("created") or _now()
        song["origin"] = "sample"
        store.save_song(song)
        added += 1
    return added
