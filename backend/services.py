"""Thin HTTP clients for the four class services.

All calls go through `_call`, which attaches the shared bearer token from
environment configuration (server-side only) and raises ServiceError with the
server's message on failure.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from . import config

TIMEOUT = config.REQUEST_TIMEOUT


class ServiceError(RuntimeError):
    """Raised when a class service returns an error or an unexpected shape."""


def _call(
    base_url: str,
    path: str,
    payload: Optional[dict] = None,
    method: str = "POST",
    timeout: int = TIMEOUT,
    raw: bool = False,
) -> Any:
    """Perform an authenticated JSON call; returns parsed JSON or raw bytes."""
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {config.require_key()}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if raw:
                return resp.status, resp.headers.get("content-type", ""), body
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500].decode("utf-8", errors="replace")
        raise ServiceError(f"{base_url}{path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ServiceError(f"{base_url}{path} -> {exc.reason}") from exc


# ---------------------------------------------------------------------------
# 9001 - Qwen3.6-35B-A3B  (text generation)
# ---------------------------------------------------------------------------
def text_completion(
    messages: list[dict],
    max_tokens: int = 1500,
    temperature: float = 0.6,
) -> str:
    """Chat completion; returns the assistant text.

    Thinking is disabled (``chat_template_kwargs.enable_thinking``) because the
    reasoning model otherwise spends the token budget on a "thinking process"
    that delays or truncates the actual answer; if the serving backend rejects
    that kwarg we transparently retry without it.
    """
    last_error: Optional[Exception] = None
    no_think = True
    for attempt in range(3):
        payload: dict[str, Any] = {
            "model": config.TEXT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if no_think:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            status, resp = _call(config.TEXT_URL, "/v1/chat/completions", payload)
            if status != 200 or not resp:
                raise ServiceError(f"text service status {status}")
            msg = resp["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            if not content:
                content = (msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
            if content:
                return content
            last_error = ServiceError("text service returned empty content")
        except ServiceError as exc:
            last_error = exc
            if no_think and "chat_template_kwargs" in str(exc):
                no_think = False  # backend does not support the kwarg; retry plainly
        except Exception as exc:  # noqa: BLE001 - retry politely
            last_error = exc
        time.sleep(1.5)
    raise ServiceError(str(last_error)) if last_error else ServiceError("text failed")


def extract_json(text: str) -> dict:
    """Parse the best JSON object in a model response.

    Tolerates thinking prose and truncated output: scans every complete JSON
    object and prefers the LAST one that carries real string content (a value
    of 10+ chars), so a quoted template/example inside the thinking phase can
    never be returned over the actual answer. Falls back to the last object.
    """
    import json as _json

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = _json.JSONDecoder()
    objects: list[tuple[dict, int]] = []  # (obj, position)
    idx = 0
    while idx < len(cleaned):
        try:
            obj, end = decoder.raw_decode(cleaned[idx:])
            if isinstance(obj, dict):
                objects.append((obj, idx))
            idx += max(end, 1)
        except _json.JSONDecodeError:
            idx += 1
    if not objects:
        raise ServiceError(f"no JSON object in model output: {text[:200]}")

    def _has_real_content(obj: dict) -> bool:
        return any(
            isinstance(v, str) and len(v) >= 10
            for v in obj.values()
        )

    substantive = [o for o, _ in objects if _has_real_content(o)]
    pool = substantive or [o for o, _ in objects]
    return pool[-1]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 9006 - FLUX.2 klein 4B  (cover art)
# ---------------------------------------------------------------------------
def generate_image(
    prompt: str,
    num_inference_steps: int = 8,
    size: str = "1024x1024",
    seed: Optional[int] = None,
) -> bytes:
    """Generate a PNG and return the raw bytes."""
    payload: dict[str, Any] = {
        "model": config.IMAGE_MODEL,
        "prompt": prompt,
        "num_inference_steps": num_inference_steps,
        "size": size,
        "response_format": "b64_json",
    }
    if seed is not None:
        payload["seed"] = seed
    status, resp = _call(config.IMAGE_URL, "/v1/images/generations", payload)
    if status != 200 or not resp or not resp.get("data"):
        raise ServiceError(f"image service returned: {str(resp)[:300]}")
    b64 = resp["data"][0].get("b64_json")
    if not b64:
        raise ServiceError("image response missing b64_json")
    return base64.b64decode(b64)


# ---------------------------------------------------------------------------
# 9007 - ACE-Step 1.5 XL Turbo  (music)
# ---------------------------------------------------------------------------
def _poll_music_task(task_id: str) -> list[dict]:
    """Poll /query_result until the task finishes; return the result items."""
    deadline = time.time() + config.MUSIC_POLL_TIMEOUT
    last_item: Optional[dict] = None
    while time.time() < deadline:
        status, resp = _call(
            config.MUSIC_URL,
            "/query_result",
            {"task_id_list": json.dumps([task_id])},
        )
        if status != 200 or not resp:
            time.sleep(config.POLL_INTERVAL)
            continue
        data = resp.get("data") if isinstance(resp, dict) else None
        items = data if isinstance(data, list) else []
        if not items:
            time.sleep(config.POLL_INTERVAL)
            continue
        item = items[0]
        last_item = item
        result_raw = item.get("result")
        if not (isinstance(result_raw, str) and result_raw.strip()):
            time.sleep(config.POLL_INTERVAL)
            continue
        try:
            parsed = json.loads(result_raw)
        except json.JSONDecodeError:
            time.sleep(config.POLL_INTERVAL)
            continue
        if not isinstance(parsed, list) or not parsed:
            time.sleep(config.POLL_INTERVAL)
            continue
        # Intermediate "Phase N: ..." items carry no file yet; only a finished
        # (or failed) item has a usable file / terminal stage.
        if any(p.get("file") for p in parsed):
            return parsed  # type: ignore[return-value]
        if any(p.get("stage") == "failed" or p.get("status") in ("failed", -1) for p in parsed):
            return parsed  # type: ignore[return-value]
        time.sleep(config.POLL_INTERVAL)
    raise ServiceError(f"music task {task_id} timed out; last status: {last_item}")


def generate_music(
    prompt: str,
    lyrics: str,
    duration: float = 25.0,
    bpm: Optional[int] = None,
    key_scale: str = "C major",
    vocal_language: str = "en",
    instrumental: bool = False,
    seed: Optional[int] = None,
) -> tuple[bytes, dict]:
    """Generate a song with ACE-Step; returns (mp3 bytes, metadata dict).

    Flow: /release_task -> /query_result (poll) -> GET file URL.
    The server can return several candidate renders; the first completed one wins.
    """
    payload: dict[str, Any] = {
        "task_type": "text2music",
        "model": config.MUSIC_MODEL,
        "prompt": prompt,
        "lyrics": lyrics if not instrumental else "",
        "audio_duration": float(duration),
        "vocal_language": vocal_language,
        "key_scale": key_scale,
        "audio_format": "mp3",
        "inference_steps": 8,
        "guidance_scale": 7.0,
        "use_random_seed": seed is None,
    }
    if bpm:
        payload["bpm"] = int(bpm)
    if seed is not None:
        payload["seed"] = int(seed)
    if instrumental:
        payload["prompt"] = f"{prompt} (instrumental track, no vocals, no singing)"

    status, resp = _call(config.MUSIC_URL, "/release_task", payload)
    if status != 200 or not isinstance(resp, dict):
        raise ServiceError(f"release_task failed: {str(resp)[:300]}")
    data = resp.get("data") or {}
    task_id = data.get("task_id")
    if not task_id:
        raise ServiceError(f"release_task missing task_id: {str(resp)[:300]}")

    items = _poll_music_task(task_id)
    chosen: Optional[dict] = None
    for item in items:
        if item.get("stage") == "failed" or item.get("status") in ("failed", -1):
            raise ServiceError(f"music generation failed: {json.dumps(item)[:400]}")
        if item.get("status") in (1, "succeeded", "done") or item.get("stage") == "succeeded":
            chosen = item
            break
    if not chosen or not chosen.get("file"):
        raise ServiceError(f"no completed audio in result: {json.dumps(items)[:500]}")

    file_url = chosen["file"]  # e.g. "/v1/audio?path=%2F...mp3"
    if not file_url.startswith("/"):
        file_url = f"/v1/audio?path={urllib.parse.quote(file_url)}"
    st, _, audio = _call(config.MUSIC_URL, file_url, method="GET", raw=True)
    if st != 200 or not audio:
        raise ServiceError(f"audio download failed (HTTP {st})")

    meta = {"seed": chosen.get("seed_value"), "meta": chosen.get("metas") or {}}
    return audio, meta


# ---------------------------------------------------------------------------
# 9008 - Chatterbox Multilingual V3  (DJ speech)
# ---------------------------------------------------------------------------
def speak(text: str, voice: str = "default", response_format: str = "mp3") -> bytes:
    """Synthesize speech; returns audio bytes."""
    status, ctype, audio = _call(
        config.VOICE_URL,
        "/v1/audio/speech",
        {
            "model": config.VOICE_MODEL,
            "input": text,
            "voice": voice or "default",
            "response_format": response_format,
            "language_id": "en",
        },
        raw=True,
    )
    if status != 200 or not audio:
        raise ServiceError(f"speech failed (HTTP {status} {ctype})")
    return audio
