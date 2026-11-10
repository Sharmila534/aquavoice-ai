"""Minimal, read-only client for Gnani Prisma V3.0 speech-to-text.

The Gnani response contract is intentionally returned as raw JSON. This keeps
the client from guessing an undocumented transcript field or response shape.
"""

from __future__ import annotations

import json
import os
import re
import uuid
import wave
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import environment  # Ensures local .env values are available when appropriate.


GNANI_STT_ENDPOINT = "https://api.vachana.ai/stt/v3"
GNANI_MODEL = "prisma-v3.0"
GNANI_FORMAT = "transcribe"
MAX_AUDIO_DURATION_SECONDS = 30.0

SUPPORTED_LANGUAGE_CODES = frozenset(
    {"indic-auto", "te-IN", "hi-IN", "ta-IN", "kn-IN", "bn-IN", "ml-IN"}
)
SUPPORTED_AUDIO_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
}


class GnaniSTTError(RuntimeError):
    """Base error for a safe, user-displayable Gnani integration failure."""


class GnaniConfigurationError(GnaniSTTError):
    """Raised when required local configuration is unavailable."""


class GnaniInputError(GnaniSTTError):
    """Raised when an audio request is outside the documented API limits."""


class GnaniServiceError(GnaniSTTError):
    """Raised when Gnani rejects a request or returns an unusable response."""


_DIAGNOSTIC_HEADER_NAMES = (
    "x-request-id",
    "request-id",
    "x-correlation-id",
    "correlation-id",
    "traceparent",
    "cf-ray",
)
_SENSITIVE_ERROR_VALUE = re.compile(
    r"(?i)([\"']?(?:x-api-key-id|authorization|api[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'}]+"
)
_MAX_ERROR_BODY_LENGTH = 1_000


def _safe_error_body(raw_body: bytes) -> str:
    """Return a bounded diagnostic body without exposing accidental secrets."""

    body = raw_body.decode("utf-8", errors="replace").strip()
    if not body:
        return ""

    body = _SENSITIVE_ERROR_VALUE.sub(r"\1[REDACTED]", body)
    body = " ".join(body.split())
    if len(body) > _MAX_ERROR_BODY_LENGTH:
        body = f"{body[:_MAX_ERROR_BODY_LENGTH]}…"
    return body


def _http_error_message(exc: HTTPError) -> str:
    """Build safe diagnostics from Gnani's HTTP error response."""

    try:
        error_body = _safe_error_body(exc.read())
    except OSError:
        error_body = ""

    headers = exc.headers
    content_type = headers.get("Content-Type", "unknown") if headers else "unknown"
    details = [f"HTTP {exc.code}", f"content_type={content_type}"]

    if headers:
        for header_name in _DIAGNOSTIC_HEADER_NAMES:
            header_value = headers.get(header_name)
            if header_value:
                details.append(f"{header_name}={header_value}")

    if error_body:
        details.append(f"server_message={error_body}")

    return "Gnani request failed: " + "; ".join(details) + "."


def _validate_duration(audio_path: Path, duration_seconds: float | None) -> float:
    """Return a verified duration without guessing compressed-audio metadata."""

    if duration_seconds is None and audio_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                duration_seconds = wav_file.getnframes() / wav_file.getframerate()
        except (wave.Error, ZeroDivisionError) as exc:
            raise GnaniInputError(
                "Could not read the WAV duration. Provide duration_seconds explicitly."
            ) from exc

    if duration_seconds is None:
        raise GnaniInputError(
            "duration_seconds is required for MP3, OGG, FLAC, AAC, and M4A files "
            "because AquaGuard does not guess compressed-audio duration."
        )

    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError) as exc:
        raise GnaniInputError("duration_seconds must be a number.") from exc

    if duration <= 0:
        raise GnaniInputError("duration_seconds must be greater than zero.")
    if duration > MAX_AUDIO_DURATION_SECONDS:
        raise GnaniInputError("Gnani Prisma V3.0 accepts audio up to 30 seconds.")

    return duration


def _multipart_body(
    *, fields: dict[str, str], audio_path: Path, mime_type: str
) -> tuple[bytes, str]:
    """Build a multipart request using only documented field names."""

    boundary = f"----AquaGuardGnani{uuid.uuid4().hex}"
    line_break = b"\r\n"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}".encode(),
                f'Content-Disposition: form-data; name="{name}"'.encode(),
                b"",
                value.encode("utf-8"),
            )
        )

    safe_filename = audio_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    chunks.extend(
        (
            f"--{boundary}".encode(),
            (
                'Content-Disposition: form-data; name="audio_file"; '
                f'filename="{safe_filename}"'
            ).encode(),
            f"Content-Type: {mime_type}".encode(),
            b"",
            audio_path.read_bytes(),
            f"--{boundary}--".encode(),
            b"",
        )
    )

    return line_break.join(chunks), boundary


def transcribe_audio(
    audio_path: str | Path,
    *,
    language_code: str = "indic-auto",
    duration_seconds: float | None = None,
    timeout_seconds: float = 45.0,
) -> Any:
    """Submit one validated audio file and return Gnani's raw JSON response.

    A successful request is not interpreted here because no vendor response JSON
    schema has been supplied to AquaGuard yet.
    """

    api_key = os.getenv("GNANI_API_KEY")
    if not api_key:
        raise GnaniConfigurationError(
            "GNANI_API_KEY is not configured. Add it to the project .env file or "
            "the current environment."
        )

    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise GnaniInputError("Audio file was not found.")

    suffix = path.suffix.lower()
    mime_type = SUPPORTED_AUDIO_TYPES.get(suffix)
    if not mime_type:
        formats = ", ".join(sorted(extension.lstrip(".").upper() for extension in SUPPORTED_AUDIO_TYPES))
        raise GnaniInputError(f"Unsupported audio format. Supported formats: {formats}.")

    if language_code not in SUPPORTED_LANGUAGE_CODES:
        raise GnaniInputError("Unsupported language_code for Gnani Prisma V3.0.")

    _validate_duration(path, duration_seconds)

    body, boundary = _multipart_body(
        fields={
            "model": GNANI_MODEL,
            "language_code": language_code,
            "format": GNANI_FORMAT,
        },
        audio_path=path,
        mime_type=mime_type,
    )
    request = Request(
        GNANI_STT_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "X-API-Key-ID": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise GnaniServiceError(_http_error_message(exc)) from exc
    except URLError as exc:
        raise GnaniServiceError("Gnani service could not be reached.") from exc
    except TimeoutError as exc:
        raise GnaniServiceError("Gnani request timed out.") from exc

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise GnaniServiceError("Gnani returned a non-JSON response.") from exc
