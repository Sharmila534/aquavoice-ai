"""Bridge recognized farmer speech into AquaGuard's existing Gemini workflow.

This module deliberately accepts an already recognized transcript. Gnani STT is
not called here, so provider-side transcription failures cannot alter the
existing AquaGuard reasoning path.
"""

from __future__ import annotations

from typing import Any

from workflow import ask_aquaguard


LANGUAGE_NAMES = {
    "te-IN": "Telugu",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "kn-IN": "Kannada",
    "bn-IN": "Bengali",
    "ml-IN": "Malayalam",
}


class AquaVoiceInputError(ValueError):
    """Raised when the caller cannot safely hand off recognized speech."""


def _validated_transcript(transcript: str) -> str:
    if not isinstance(transcript, str) or not transcript.strip():
        raise AquaVoiceInputError("A non-empty recognized transcript is required.")
    return transcript.strip()


def _response_language(detected_language: str) -> str:
    try:
        return LANGUAGE_NAMES[detected_language]
    except KeyError as exc:
        supported = ", ".join(sorted(LANGUAGE_NAMES))
        raise AquaVoiceInputError(
            "detected_language must be a concrete supported Gnani language code "
            f"({supported}); indic-auto is not a final detected language."
        ) from exc


async def respond_to_transcript(
    transcript: str,
    detected_language: str,
    pond_information: dict[str, Any] | None = None,
    *,
    user_id: str = "aquavoice",
    session_id: str | None = None,
) -> tuple[str, str]:
    """Use the existing AquaGuard root agent to answer recognized speech.

    ``pond_information`` is optional. When absent, the reasoning workflow is
    intentionally given an empty context rather than invented farm data.
    """

    farmer_question = _validated_transcript(transcript)
    response_language = _response_language(detected_language)
    farm_context = pond_information if pond_information is not None else {}
    if not isinstance(farm_context, dict):
        raise AquaVoiceInputError("pond_information must be a dictionary when supplied.")

    return await ask_aquaguard(
        question=farmer_question,
        farm_data=farm_context,
        user_id=user_id,
        session_id=session_id,
        response_language=response_language,
    )
