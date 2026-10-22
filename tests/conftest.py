"""Shared pytest fixtures.

All tests run fully offline: every call to the class services is mocked or
monkeypatched, and storage is pointed at a per-test tmp dir so the developer's
real `storage/` library is never touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pytest  # noqa: E402

from backend import config  # noqa: E402


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """Point the whole storage layer at a throwaway directory."""
    root = tmp_path / "storage"
    monkeypatch.setattr(config, "STORAGE_DIR", root)
    monkeypatch.setattr(config, "LIBRARY_FILE", root / "library.json")
    monkeypatch.setattr(config, "SHOWS_FILE", root / "shows.json")
    monkeypatch.setattr(config, "PLAYLISTS_FILE", root / "playlists.json")
    return root
