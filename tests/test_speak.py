"""The 9008 speech client: payload shape for default vs customized calls."""
from backend import config, services


def _capture(monkeypatch):
    captured = {}

    def fake_call(base, path, payload=None, method="POST", timeout=None, raw=False):
        captured["payload"] = payload
        return 200, "audio/mpeg", b"<audio>"

    monkeypatch.setattr(services, "_call", fake_call)
    return captured


def test_speak_default_payload(monkeypatch):
    captured = _capture(monkeypatch)
    out = services.speak("Hello, listeners!")
    assert out == b"<audio>"
    assert captured["payload"]["input"] == "Hello, listeners!"
    assert captured["payload"]["voice"] == "default"
    assert "ref_audio" not in captured["payload"]
    assert "speed" not in captured["payload"]


def test_speak_with_reference_and_speed(monkeypatch):
    captured = _capture(monkeypatch)
    services.speak("Hi", ref_audio="REFDATA==", speed=0.9)
    assert captured["payload"]["ref_audio"] == "REFDATA=="
    assert captured["payload"]["speed"] == 0.9


def test_speak_omits_optional_fields_when_unset(monkeypatch):
    captured = _capture(monkeypatch)
    services.speak("Hi", ref_audio="", speed=None)
    assert "ref_audio" not in captured["payload"]
    assert "speed" not in captured["payload"]
