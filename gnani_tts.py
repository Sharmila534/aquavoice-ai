"""Minimal Gnani Timbre REST client for AquaVoice playback."""

from __future__ import annotations

import json
import os
import re
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import environment  # Ensures local .env values are available when appropriate.


GNANI_TTS_ENDPOINT: Final = "https://api.vachana.ai/api/v1/tts/inference"
TTS_MODEL: Final = "timbre-v3.0"
TTS_VOICE: Final = "Shivani"
TTS_LANGUAGE: Final = "te-IN"
_EXPECTED_CONTENT_TYPE: Final = "audio/wav"
_MAX_ERROR_BODY_LENGTH: Final = 1_000
_SENSITIVE_ERROR_VALUE = re.compile(
    r"(?i)([\"']?(?:x-api-key-id|authorization|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'}]+"
)


class GnaniTTSError(RuntimeError):
    """Base error for a safe, user-displayable Gnani TTS failure."""


class GnaniTTSConfigurationError(GnaniTTSError):
    """Raised when required local TTS configuration is unavailable."""


class GnaniTTSInputError(GnaniTTSError):
    """Raised when caller-provided TTS text is unusable."""


class GnaniTTSServiceError(GnaniTTSError):
    """Raised when Gnani rejects a TTS request or returns invalid audio."""


def _safe_error_body(raw_body: bytes) -> str:
    """Return bounded provider diagnostics without exposing credentials."""

    body = raw_body.decode("utf-8", errors="replace").strip()
    if not body:
        return ""

    body = _SENSITIVE_ERROR_VALUE.sub(r"\1[REDACTED]", body)
    body = " ".join(body.split())
    if len(body) > _MAX_ERROR_BODY_LENGTH:
        body = f"{body[:_MAX_ERROR_BODY_LENGTH]}…"
    return body


def _http_error_message(exc: HTTPError) -> str:
    """Return a concise diagnostic without headers or credentials."""

    try:
        body = _safe_error_body(exc.read())
    except OSError:
        body = ""

    message = f"Gnani TTS request failed with HTTP {exc.code}."
    return f"{message} Provider message: {body}" if body else message


def synthesize_speech(text: str, *, timeout_seconds: float = 45.0) -> bytes:
    """Synthesize one complete Telugu AquaGuard answer as a WAV response.

    Exactly one HTTP request is made. The caller owns playback and any optional
    local file persistence.
    """

    if not isinstance(text, str) or not text.strip():
        raise GnaniTTSInputError("A non-empty AquaGuard answer is required for speech.")
    if timeout_seconds <= 0:
        raise GnaniTTSInputError("timeout_seconds must be greater than zero.")

    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise GnaniTTSConfigurationError(
            "GNANI_API_KEY is not configured. Add it to the project .env file or "
            "the current environment."
        )

    payload = {
        "text": text.strip(),
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "language": TTS_LANGUAGE,
        "speed": 1.0,
        "audio_config": {
            "sample_rate": 24000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    request = Request(
        GNANI_TTS_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": _EXPECTED_CONTENT_TYPE,
            "X-API-Key-ID": api_key,
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            audio_bytes = response.read()
    except HTTPError as exc:
        raise GnaniTTSServiceError(_http_error_message(exc)) from exc
    except URLError as exc:
        raise GnaniTTSServiceError("Gnani TTS service could not be reached.") from exc
    except TimeoutError as exc:
        raise GnaniTTSServiceError("Gnani TTS request timed out.") from exc
    except OSError as exc:
        raise GnaniTTSServiceError("Gnani TTS request could not complete.") from exc

    if status != 200:
        raise GnaniTTSServiceError(f"Gnani TTS returned unexpected HTTP status {status}.")
    if content_type.lower() != _EXPECTED_CONTENT_TYPE:
        raise GnaniTTSServiceError("Gnani TTS returned an unexpected response content type.")
    if not audio_bytes:
        raise GnaniTTSServiceError("Gnani TTS returned an empty audio response.")

    return audio_bytes
