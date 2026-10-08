"""ThemePool: instant 'random theme' rolls backed by a warm pool of AI ideas.

The class text model takes ~15-25s per generation, too slow for a dice-roll
button. Instead a small background pool keeps 2-3 fresh themes ready; every
roll pops instantly and triggers a background refill. When the pool is empty
or the text service is down, a hand-picked fallback theme is served so the
button never dead-ends.
"""
from __future__ import annotations

import json
import random
import threading
from typing import Optional

from . import prompts, services

FALLBACKS = [
    "stargazing on a rooftop in the rain",
    "a midnight diner that only opens when it snows",
    "chasing the last train out of the city",
    "a lighthouse keeper's 4 a.m. broadcast",
    "driving through the desert with the top down",
    "a love letter written on a torn napkin",
    "the arcade at the end of summer",
    "waves at an empty beach at dawn",
    "robots learning to dance",
    "the smell of rain on hot pavement",
    "a jazz club visible only on foggy nights",
    "a spaceship garden growing earth flowers",
    "an old cassette tape found in a thrift store",
    "a bicycle ride through cherry blossom streets",
    "a midnight bakery with a secret menu",
    "a postcard from a city you have never seen",
    "the graveyard shift at a 24-hour laundromat",
    "sailing across a sea of clouds",
    "a campfire story that changes every telling",
    "moths circling a porch light in July",
]

_NO_ECHO = (
    "3-8 words", "lower-case", "your theme here",
    "lighthouse keeper's 4 a.m. broadcast",
)

_WARM_COUNT = 3     # themes each background refill tries to add
_REFILL_AT = 1      # start a refill when fewer than this many are left


def _last_json(text: str) -> Optional[dict]:
    """Parse the LAST complete JSON object in a model response.

    The text service on this class host streams the model's whole internal
    deliberation into the response and never flushes a separate content field,
    so the model's actual answer (its final pick) sits at the very end.
    """
    decoder = json.JSONDecoder()
    found: Optional[dict] = None
    idx = 0
    while True:
        idx = text.find("{", idx)
        if idx == -1:
            break
        try:
            obj, end = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                found = obj
            idx += end
        except json.JSONDecodeError:
            idx += 1
    return found


def _ask_text_model() -> Optional[str]:
    """Roll one theme from the text model, or None when it doesn't produce one."""
    raw = services.text_completion(
        [
            {"role": "system", "content": prompts.THEME_SYSTEM},
            {"role": "user", "content": prompts.THEME_USER},
        ],
        max_tokens=2048,
        temperature=1.0,
    )
    obj = _last_json(raw) or {}
    theme = " ".join(str(obj.get("theme", "")).split())
    if 1 < len(theme) <= 120 and not any(t in theme for t in _NO_ECHO):
        return theme
    return None


class ThemePool:
    """Thread-safe pool of ready-to-serve AI themes with background refills."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._themes: list[str] = []
        self._refilling = False
        threading.Thread(target=self._refill, daemon=True).start()

    def next(self) -> str:
        with self._lock:
            theme = self._themes.pop() if self._themes else None
            if len(self._themes) < _REFILL_AT and not self._refilling:
                self._refilling = True
                threading.Thread(target=self._refill, daemon=True).start()
        return theme or random.choice(FALLBACKS)

    def _refill(self) -> None:
        try:
            for _ in range(_WARM_COUNT):
                try:
                    theme = _ask_text_model()
                except services.ServiceError:
                    continue  # service hiccup: try the next one in the batch
                if theme:
                    with self._lock:
                        self._themes.append(theme)
        finally:
            with self._lock:
                self._refilling = False
