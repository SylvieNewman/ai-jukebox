"""End-to-end smoke test for the AI Jukebox class services.

Verifies that all four class services respond correctly from this machine:
  9001 text (Qwen3.6-35B-A3B)   -> writes a lyric snippet
  9006 image (FLUX.2 klein 4B)  -> renders cover art (PNG)
  9007 music (ACE-Step 1.5 XL)  -> composes a short instrumental (MP3)
  9008 voice (Chatterbox V3)    -> speaks a DJ line (MP3)

Usage:  python scripts/smoke_test.py          (needs .env configured)
Output: ./smoke-out/  (gitignored)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import services  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "smoke-out"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    failures = 0

    # 1. Text
    try:
        text = services.text_completion(
            [{"role": "user", "content":
              "Reply with exactly this JSON, nothing else: {\"ok\": \"juice\"}"}],
            max_tokens=80, temperature=0.0,
        )
        parsed = services.extract_json(text)
        assert parsed.get("ok") == "juice", parsed
        print("[OK] 9001 text  ->", parsed)
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print("[FAIL] 9001 text ->", exc)

    # 2. Cover art
    try:
        png = services.generate_image("a tiny neon jukebox on a dark street, album art, no text",
                                      num_inference_steps=8)
        (OUT / "cover.png").write_bytes(png)
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10_000, f"bad png ({len(png)}B)"
        print(f"[OK] 9006 image -> {OUT / 'cover.png'} ({len(png) // 1024} KB)")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print("[FAIL] 9006 image ->", exc)

    # 3. Music (short instrumental)
    try:
        mp3, meta = services.generate_music(
            prompt="a short chill lo-fi instrumental with soft keys",
            lyrics="", duration=10.0, vocal_language="en", instrumental=True,
        )
        (OUT / "music.mp3").write_bytes(mp3)
        assert len(mp3) > 20_000, f"audio too small ({len(mp3)}B)"
        print(f"[OK] 9007 music -> {OUT / 'music.mp3'} ({len(mp3) // 1024} KB) seed={meta.get('seed')}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print("[FAIL] 9007 music ->", exc)

    # 4. DJ voice
    try:
        mp3 = services.speak("Testing one two three. The jukebox is alive.")
        (OUT / "dj.mp3").write_bytes(mp3)
        assert mp3[:3] == b"ID3" and len(mp3) > 10_000, f"bad mp3 ({len(mp3)}B)"
        print(f"[OK] 9008 voice -> {OUT / 'dj.mp3'} ({len(mp3) // 1024} KB)")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print("[FAIL] 9008 voice ->", exc)

    print("\n" + ("ALL SERVICES OK" if failures == 0 else f"{failures} SERVICE(S) FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
