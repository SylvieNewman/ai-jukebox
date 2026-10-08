"""Server-side configuration for the AI Jukebox.

All credentials are read from environment variables / the local .env file.
Nothing secret is ever hard-coded, logged, or served to the browser.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover - dotenv optional at import time
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Class service endpoints (see class-endpoints.txt.example / .env) -------
# Port 9000 is deliberately never used (class rule). No values are hard-coded:
# everything comes from the environment, and configuration examples use
# placeholders only.
TEXT_URL = os.environ.get("JUKEBOX_TEXT_URL", "")
IMAGE_URL = os.environ.get("JUKEBOX_IMAGE_URL", "")
MUSIC_URL = os.environ.get("JUKEBOX_MUSIC_URL", "")
VOICE_URL = os.environ.get("JUKEBOX_VOICE_URL", "")

# --- Credentials: env only, never committed ---------------------------------
API_KEY = (
    os.environ.get("JUKEBOX_API_KEY")
    or os.environ.get("HERMES_CUSTOM_DOBOLYI_COM_9000_API_KEY")
    or ""
)

# --- Model IDs (class services) ----------------------------------------------
TEXT_MODEL = os.environ.get("JUKEBOX_TEXT_MODEL", "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit")
IMAGE_MODEL = os.environ.get("JUKEBOX_IMAGE_MODEL", "black-forest-labs/FLUX.2-klein-4B")
MUSIC_MODEL = os.environ.get("JUKEBOX_MUSIC_MODEL", "acestep-v15-xl-turbo")
VOICE_MODEL = os.environ.get("JUKEBOX_VOICE_MODEL", "chatterbox-v3")
VOICE = os.environ.get("JUKEBOX_VOICE", "default")

# --- Storage -----------------------------------------------------------------
STORAGE_DIR = Path(os.environ.get("JUKEBOX_STORAGE", PROJECT_ROOT / "storage"))
LIBRARY_FILE = STORAGE_DIR / "library.json"
SHOWS_FILE = STORAGE_DIR / "shows.json"
PLAYLISTS_FILE = STORAGE_DIR / "playlists.json"

# --- Tuning ------------------------------------------------------------------
REQUEST_TIMEOUT = int(os.environ.get("JUKEBOX_REQUEST_TIMEOUT", "420"))
POLL_INTERVAL = float(os.environ.get("JUKEBOX_POLL_INTERVAL", "2.5"))
MUSIC_POLL_TIMEOUT = int(os.environ.get("JUKEBOX_MUSIC_POLL_TIMEOUT", "360"))
# DJ speech pacing (Chatterbox accepts 0.25-4.0; 1.0 = server default, which
# sounds rushed, so we default to a more relaxed 0.9x).
DJ_SPEED = float(os.environ.get("JUKEBOX_DJ_SPEED", "0.9"))

# Languages supported by the Chatterbox endpoint (/info). Code -> display name.
DJ_LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "hi": "Hindi", "ar": "Arabic", "ru": "Russian",
    "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "tr": "Turkish",
    "da": "Danish", "fi": "Finnish", "el": "Greek", "he": "Hebrew",
    "ms": "Malay", "no": "Norwegian", "sw": "Swahili",
}
CJK_LANGUAGES = frozenset({"ja", "zh", "ko"})


def require_key() -> str:
    """Fail fast with a clear message if no API key is configured."""
    if not API_KEY:
        raise RuntimeError(
            "No API key configured. Copy .env.example to .env and set "
            "JUKEBOX_API_KEY (or export HERMES_CUSTOM_DOBOLYI_COM_9000_API_KEY)."
        )
    return API_KEY


def validate() -> None:
    """Called at app startup: every service URL must be configured."""
    missing = [
        name
        for name, value in {
            "JUKEBOX_TEXT_URL": TEXT_URL,
            "JUKEBOX_IMAGE_URL": IMAGE_URL,
            "JUKEBOX_MUSIC_URL": MUSIC_URL,
            "JUKEBOX_VOICE_URL": VOICE_URL,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing environment configuration: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in your class endpoint URLs."
        )
    require_key()
