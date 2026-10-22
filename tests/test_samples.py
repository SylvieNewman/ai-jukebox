"""Sample-song seeding: a fresh library must get exactly the three bundled
samples, and re-seeding must never duplicate them."""
from backend import samples, store


def test_seed_adds_exactly_three_samples(storage):
    added = samples.seed_samples()
    assert added == 3
    songs = store.list_songs()
    assert len(songs) == 3
    for s in songs:
        assert s["origin"] == "sample"
        assert s["title"] and s["artist"]
        assert store.song_file(s["id"], "audio.mp3").is_file()
        assert store.song_file(s["id"], "cover.jpg").is_file()


def test_seed_is_idempotent(storage):
    assert samples.seed_samples() == 3
    assert samples.seed_samples() == 0
    assert len(store.list_songs()) == 3
