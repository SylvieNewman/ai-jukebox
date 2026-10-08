"""SuggestionPool: instant random suggestions backed by warm pools of AI ideas.

The class text model takes ~15-25s per generation, too slow for dice-roll
buttons. Instead each pool keeps a few fresh ideas ready; every roll pops
instantly and triggers a background refill. When a pool is empty or the text
service is down, a hand-picked fallback is served so the button never
dead-ends.
"""
from __future__ import annotations

import json
import random
import threading
from typing import Callable, Generic, Optional, TypeVar

from . import prompts, services

T = TypeVar("T")

# ------------------------------------------------------------------ themes --
THEME_FALLBACKS = [
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

# ------------------------------------------------------------- artist/title --
NAME_FALLBACKS = [
    ("Aurora Static", "Glass Sundown"),
    ("Marlow Finch", "The Last Overpass"),
    ("Coco Halo", "Popcorn & Static"),
    ("June Arcade", "Credit to the Moon"),
    ("Reverie Thew", "Paperback Hearts"),
    ("Kit Polar", "Radio Snow"),
    ("Sunday Meridian", "Twice Around the Block"),
    ("Lumen Vale", "Fault Lines of Summer"),
    ("Petra Wavelength", "Half a Second of Light"),
    ("Orson Mono", "Letters in Low Tide"),
    ("Vega Nine", "Neon Birdhouse"),
    ("Callie Drift", "Every Exit Looks Alike"),
    ("The Paper Comets", "One Quiet Alarm"),
    ("Sable Almanac", "The Year of Small Ferries"),
    ("Nova Brass & the Arps", "Slow Dance on a Fast Planet"),
]

# ------------------------------------------------------------------ helpers --

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


def _ask_text_model(system: str, user: str, max_tokens: int = 2048) -> str:
    return services.text_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=1.0,
    )


def ask_theme() -> Optional[str]:
    """Roll one theme from the text model, or None when it doesn't produce one."""
    raw = _ask_text_model(prompts.THEME_SYSTEM, prompts.THEME_USER)
    obj = _last_json(raw) or {}
    theme = " ".join(str(obj.get("theme", "")).split())
    no_echo = ("3-8 words", "lower-case", "your theme here", "a lighthouse keeper's 4 a.m. broadcast")
    if 1 < len(theme) <= 120 and not any(t in theme for t in no_echo):
        return theme
    return None


def ask_name_pair() -> Optional[tuple[str, str]]:
    """Roll one (artist, title) pair from the text model, or None on failure."""
    raw = _ask_text_model(prompts.NAME_SYSTEM, prompts.NAME_USER)
    obj = _last_json(raw) or {}
    artist = " ".join(str(obj.get("artist", "")).split())
    title = " ".join(str(obj.get("title", "")).split())
    no_echo = ("your artist here", "your title here", "neon daze", "midnight colors")
    ok = (
        1 < len(artist) <= 60 and 1 < len(title) <= 60
        and not any(t in artist.lower() for t in no_echo)
        and not any(t in title.lower() for t in no_echo)
    )
    return (artist, title) if ok else None


# ------------------------------------------------------------------ the pool --
class SuggestionPool(Generic[T]):
    """Thread-safe pool of ready-to-serve suggestions with background refills."""

    def __init__(
        self,
        ask: Callable[[], Optional[T]],
        fallbacks: list[T],
        warm_count: int = 3,
        refill_at: int = 1,
    ) -> None:
        self._ask = ask
        self._fallbacks = fallbacks
        self._warm_count = warm_count
        self._refill_at = refill_at
        self._lock = threading.Lock()
        self._items: list[T] = []
        self._refilling = False
        threading.Thread(target=self._refill, daemon=True).start()

    def next(self) -> T:
        with self._lock:
            item = self._items.pop() if self._items else None
            if len(self._items) < self._refill_at and not self._refilling:
                self._refilling = True
                threading.Thread(target=self._refill, daemon=True).start()
        return item if item is not None else random.choice(self._fallbacks)

    def _refill(self) -> None:
        try:
            for _ in range(self._warm_count):
                try:
                    item = self._ask()
                except services.ServiceError:
                    continue  # service hiccup: try the next one in the batch
                if item:
                    with self._lock:
                        self._items.append(item)
        finally:
            with self._lock:
                self._refilling = False
