"""Song / show generation pipeline.

generate_song:  Qwen writes lyrics+caption+cover prompt -> ACE-Step renders the
                music and FLUX paints the cover (in parallel) -> everything is
                saved under storage/ and indexed in the local library.
generate_show:  N songs + spoken DJ segues (Chatterbox) -> a playable set.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from . import config, prompts, services, store

# ACE-Step vocal language codes (music service on :9007) for the languages the
# frontend offers. Anything unknown safely falls back to English.
VOCAL_LANGUAGE_CODES = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Japanese": "ja",
    "Korean": "ko",
    "Chinese (Mandarin)": "zh",
    "Russian": "ru",
}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _json_completion(
    messages: list[dict], max_tokens: int, temperature: float
) -> dict:
    """Run the model and extract JSON, retrying when a thinking-heavy response
    truncates before the JSON object completes."""
    last_error: Optional[BaseException] = None
    for _ in range(3):
        try:
            text = services.text_completion(messages, max_tokens=max_tokens,
                                            temperature=temperature)
            return services.extract_json(text)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            import time as _time
            _time.sleep(2)
    raise services.ServiceError(f"model JSON extraction failed after retries: {last_error}")


def _lyrics_from_model(
    genre: str,
    mood: str,
    theme: str,
    duration: float,
    vocals: bool,
    language: str = "English",
    artist_hint: str = "",
    title_hint: str = "",
) -> dict:
    extra = ""
    if artist_hint:
        extra += f"\nUse this artist name: {artist_hint}"
    if title_hint:
        extra += f"\nUse this title: {title_hint}"
    language_line = f"Vocal language: {language}" if vocals else "Instrumental: no vocals anywhere"
    user = prompts.SONGWRITER_USER.format(
        genre=genre,
        mood=mood,
        theme=theme,
        duration=int(round(duration)),
        vocals_hint="lead vocals with lyrics" if vocals else "instrumental only, no singing",
        language_line=language_line,
        extra=extra,
    )
    data = _json_completion(
        [{"role": "system", "content": prompts.SONGWRITER_SYSTEM},
         {"role": "user", "content": user}],
        max_tokens=4000,
        temperature=0.7,
    )
    for field in ("title", "artist", "lyrics", "caption", "cover_prompt"):
        if not data.get(field):
            raise services.ServiceError(f"songwriter JSON missing '{field}'")

    # Keep the model honest about the requested duration: cap lyric length.
    max_lines = max(4, int(round(duration / 5)))
    lyrics = "\n".join(data["lyrics"].splitlines()[: max_lines + 12])
    data["lyrics"] = lyrics
    return data


def generate_song(
    genre: str = "pop",
    mood: str = "upbeat",
    theme: str = "driving at night",
    duration: float = 25.0,
    vocals: bool = True,
    language: str = "English",
    bpm: Optional[int] = None,
    key_scale: str = "C major",
    cover_style: str = "vibrant album art",
    artist_hint: str = "",
    title_hint: str = "",
    seed: Optional[int] = None,
) -> dict:
    """Create one complete song (lyrics + music + cover) and store it."""
    blueprint = _lyrics_from_model(
        genre, mood, theme, duration, vocals, language=language,
        artist_hint=artist_hint, title_hint=title_hint,
    )

    music_prompt = blueprint["caption"]
    cover_prompt = (
        f"{blueprint['cover_prompt']}. Art direction: {cover_style}, "
        f"album cover, square, no text."
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        music_future = pool.submit(
            services.generate_music,
            music_prompt,
            blueprint["lyrics"] if vocals else "",
            duration=duration,
            bpm=bpm,
            key_scale=key_scale,
            vocal_language=VOCAL_LANGUAGE_CODES.get(language, "en"),
            instrumental=not vocals,
            seed=seed,
        )
        cover_future = pool.submit(services.generate_image, cover_prompt, seed=seed)

    audio, music_meta = music_future.result()
    cover_bytes = cover_future.result()

    song_dir = store.new_song_dir()
    song_id = song_dir.name  # storage path and public id are the same
    (song_dir / "audio.mp3").write_bytes(audio)
    (song_dir / "cover.png").write_bytes(cover_bytes)

    song = {
        "id": song_id,
        "title": blueprint["title"].strip().strip('"'),
        "artist": blueprint["artist"].strip().strip('"'),
        "genre": genre,
        "mood": mood,
        "theme": theme,
        "bpm": bpm,
        "key": key_scale,
        "duration": round(duration),
        "vocals": vocals,
        "language": language,
        "lyrics": blueprint["lyrics"],
        "caption": blueprint["caption"],
        "cover_prompt": blueprint["cover_prompt"],
        "cover_url": f"/media/songs/{song_id}/cover.png",
        "audio_url": f"/media/songs/{song_id}/audio.mp3",
        "created": _now(),
        "music_meta": music_meta or {},
    }
    return store.save_song(song)


# ---------------------------------------------------------------------------
# Shows
# ---------------------------------------------------------------------------
_FORBIDDEN_SCRIPT_TOKENS = ("...", "placeholder", "lorem", "the previous track ",
                           "the following track", "insert", "replace me")

_RETRY_NUDGE = """

Your previous attempt was rejected: lines were placeholders, ellipses, or simply
too short. Write the complete lines NOW — full sentences in {language_name},
3-5 sentences per line, closing out the real previous song and introducing
the real next song by title and artist."""


def _valid_script(text: str, language: str = "en") -> bool:
    """A DJ line must be real, substantial broadcast copy — not a placeholder.

    Thresholds are language-aware: CJK packs more meaning per character and
    does not split on spaces like the Latin scripts.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if any(tok in low for tok in _FORBIDDEN_SCRIPT_TOKENS):
        return False
    if language in config.CJK_LANGUAGES:
        sentence_enders = sum(1 for ch in t if ch in "。！？．.!?")
        return len(t) >= 60 and sentence_enders >= 2
    return len(t) >= 100 and len(t.split()) >= 14


def _dj_scripts(songs: list[dict], dj_vibe: str, dj_language: str = "en") -> dict:
    """Opener + one segue per track after the first, written in the chosen
    language, validated and retried so a placeholder/one-word line can never
    reach the player."""
    if dj_language not in config.DJ_LANGUAGES:
        dj_language = "en"
    language_name = config.DJ_LANGUAGES[dj_language]
    min_chars = 60 if dj_language in config.CJK_LANGUAGES else 100
    n_segues = max(0, len(songs) - 1)
    playlist = "\n".join(
        f'{i + 1}. "{s["title"]}" by {s["artist"]} ({s["genre"]}, {s["mood"]}, {s["theme"]})'
        for i, s in enumerate(songs)
    )
    base_user = prompts.SHOW_USER.format(
        playlist=playlist, n_segues=n_segues,
        dj_language_name=language_name, min_chars=min_chars,
    )
    nudge = ""
    last_error = "no attempt made"

    for attempt in range(5):
        try:
            scripts = services.extract_json(services.text_completion(
                [{"role": "system",
                  "content": prompts.SHOW_SYSTEM.format(
                      dj_vibe=dj_vibe, dj_language_name=language_name)},
                 {"role": "user", "content": base_user + nudge}],
                max_tokens=2400,
                temperature=0.85,
            ))
        except Exception as exc:  # noqa: BLE001 - unparseable output, retry
            last_error = f"attempt {attempt + 1}: {exc}"
            nudge = _RETRY_NUDGE.format(language_name=language_name)
            continue

        opener = str(scripts.get("opener") or "").strip()
        raw_segues = scripts.get("segues")
        segues = [str(x).strip() for x in raw_segues] if isinstance(raw_segues, list) else []
        lengths = [len(x) for x in [opener, *segues[:n_segues]]]
        if _valid_script(opener, dj_language) and len(segues) >= n_segues and all(
            _valid_script(s, dj_language) for s in segues[:n_segues]
        ):
            return {"opener": opener, "segues": segues[:n_segues]}
        last_error = f"attempt {attempt + 1}: script quality too low (chars={lengths})"
        nudge = _RETRY_NUDGE.format(language_name=language_name)

    raise services.ServiceError(f"DJ script generation failed after 5 attempts: {last_error}")


def generate_show(
    n_tracks: int = 3,
    genre: str = "pop",
    mood: str = "upbeat",
    theme: str = "driving at night",
    duration: float = 25.0,
    vocals: bool = True,
    language: str = "English",
    bpm: Optional[int] = None,
    key_scale: str = "C major",
    cover_style: str = "vibrant album art",
    dj_vibe: str = "chill and smooth",
    dj_language: str = "en",
    dj_speed: Optional[float] = None,
    artist_hint: str = "",
) -> dict:
    """Build a whole radio set: songs first, then AI DJ commentary between them.

    The DJ speaks in ``dj_language`` (a Chatterbox language code from
    ``config.DJ_LANGUAGES``) at ``dj_speed`` (None = the config default, which
    is a relaxed 0.9x rather than the service's rushed 1.0).
    """
    if dj_language not in config.DJ_LANGUAGES:
        dj_language = "en"
    n_tracks = max(1, min(int(n_tracks), 6))
    with ThreadPoolExecutor(max_workers=min(2, n_tracks)) as pool:  # be polite to the queue
        songs = list(pool.map(
            lambda i: generate_song(
                genre=genre, mood=mood, theme=theme, duration=duration,
                vocals=vocals, language=language, bpm=bpm, key_scale=key_scale,
                cover_style=cover_style, artist_hint=artist_hint,
            ),
            range(n_tracks),
        ))

    scripts = _dj_scripts(songs, dj_vibe, dj_language)
    opener = scripts.get("opener", "").strip()
    segues = scripts.get("segues", []) if isinstance(scripts.get("segues"), list) else []
    segues = [str(s).strip() for s in segues[: n_tracks - 1]]
    while len(segues) < n_tracks - 1:
        segues.append("And now, the next track on the jukebox.")

    show_id = uuid.uuid4().hex[:12]
    show_dir = config.STORAGE_DIR / "shows" / show_id
    show_dir.mkdir(parents=True, exist_ok=True)

    segments: list[dict] = []
    if opener:
        audio_bytes = services.speak(opener, language=dj_language, speed=dj_speed)
        fname = f"segment_0_first.mp3"
        (show_dir / fname).write_bytes(audio_bytes)
        segments.append({"kind": "dj", "label": "Opening", "script": opener,
                         "audio_url": f"/media/shows/{show_id}/{fname}"})
    for track_index, song in enumerate(songs):  # 0-based
        segments.append({"kind": "song", "song_id": song["id"], "label": f"Track {track_index + 1}",
                         "title": song["title"], "artist": song["artist"],
                         "audio_url": song["audio_url"], "cover_url": song["cover_url"],
                         "lyrics": song["lyrics"]})
        if track_index < n_tracks - 1 and track_index < len(segues):
            script = segues[track_index]
            audio_bytes = services.speak(script, language=dj_language, speed=dj_speed)
            fname = f"segment_{track_index + 1}_{len(segments)}.mp3"
            (show_dir / fname).write_bytes(audio_bytes)
            segments.append({"kind": "dj", "label": f"Segue into track {track_index + 2}",
                             "script": script,
                             "audio_url": f"/media/shows/{show_id}/{fname}"})

    show = {
        "id": show_id,
        "name": f"{mood.title()} {theme.title()} — {n_tracks}-track AI set"
                + (f" · {config.DJ_LANGUAGES[dj_language]}" if dj_language != "en" else ""),
        "genre": genre, "mood": mood, "theme": theme, "dj_vibe": dj_vibe,
        "dj_language": dj_language, "dj_speed": dj_speed,
        "segments": segments,
        "song_ids": [s["id"] for s in songs],
        "created": _now(),
    }
    return store.save_show(show)
