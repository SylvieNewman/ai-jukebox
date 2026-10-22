"""Show generation: partial-failure recovery, voice-reference forwarding,
DJ-speed forwarding, and song-specific DJ prompts. All offline (mocked)."""
import json

import pytest

from backend import config, generator, services

_OPENER = ("Welcome to the AI jukebox, where every single track you are about "
           "to hear tonight was composed, written, and produced entirely by "
           "machines, so settle in and enjoy the ride.")


def _fake_song(i: int) -> dict:
    return {
        "id": f"song-{i}", "title": f"Track {i}", "artist": "Test Artist",
        "genre": "pop", "mood": "upbeat", "theme": "test theme",
        "duration": 25, "vocals": True, "language": "English",
        "lyrics": "la la la", "caption": f"caption text for track number {i}",
        "cover_url": f"/media/songs/song-{i}/cover.png",
        "audio_url": f"/media/songs/song-{i}/audio.mp3",
        "created": f"2026-01-01T00:00:0{i}Z",
    }


def _patch_dj(monkeypatch):
    def fake_dj(songs, dj_vibe):
        segues = [
            f"Up next is the wonderful {songs[i + 1]['title']} by Test Artist and "
            f"I simply cannot wait to hear it, no really, this one is going to be "
            f"special tonight."
            for i in range(len(songs) - 1)
        ]
        return {"opener": _OPENER, "segues": segues}

    monkeypatch.setattr(generator, "_dj_scripts", fake_dj)


def test_partial_failure_keeps_set_alive(storage, monkeypatch):
    calls = {"n": 0}

    def flaky(**kwargs):
        i = calls["n"]
        calls["n"] += 1
        if i == 1:
            raise services.ServiceError("music service boom")
        return _fake_song(i)

    spoken = []
    monkeypatch.setattr(generator, "generate_song", flaky)
    monkeypatch.setattr(services, "speak",
                        lambda text, **kw: spoken.append((text, kw)) or b"<audio>")
    _patch_dj(monkeypatch)

    show = generator.generate_show(n_tracks=3, voice_ref_b64="REFX", theme="test")

    assert len(show["errors"]) == 1 and "track 2" in show["errors"][0]
    assert show["song_ids"] == ["song-0", "song-2"]
    assert show["name"].endswith("— 2-track AI set")
    assert [s["kind"] for s in show["segments"]] == ["dj", "song", "dj", "song"]
    # the voice reference must be forwarded to every speech call
    assert spoken and all(kw.get("ref_audio") == "REFX" for _, kw in spoken)


def test_all_tracks_fail_raises(storage, monkeypatch):
    def boom(**kwargs):
        raise services.ServiceError("service down")

    monkeypatch.setattr(generator, "generate_song", boom)
    with pytest.raises(services.ServiceError, match="all 3 tracks failed"):
        generator.generate_show(n_tracks=3)


def test_dj_speed_forwarded_when_configured(storage, monkeypatch):
    monkeypatch.setattr(config, "DJ_SPEED", 0.8)
    spoken = []
    monkeypatch.setattr(generator, "generate_song", lambda **kw: _fake_song(0))
    monkeypatch.setattr(services, "speak",
                        lambda text, **kw: spoken.append((text, kw)) or b"<audio>")
    _patch_dj(monkeypatch)

    generator.generate_show(n_tracks=1)
    assert spoken and all(kw.get("speed") == 0.8 for _, kw in spoken)


def test_dj_prompt_includes_song_specific_caption(monkeypatch):
    captured = {}

    def fake_completion(messages, max_tokens=2400, temperature=0.85):
        captured["user"] = messages[-1]["content"]
        return json.dumps({"opener": _OPENER, "segues": []})

    monkeypatch.setattr(services, "text_completion", fake_completion)
    generator._dj_scripts([_fake_song(3)], "chill and smooth")
    assert "sounds like: caption text for track number 3" in captured["user"]
