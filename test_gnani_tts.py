"""One-request manual Gnani Timbre smoke test. This is not run by the app."""

from __future__ import annotations

from pathlib import Path

from gnani_tts import GnaniTTSError, synthesize_speech


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_ROOT / "artifacts" / "gnani_tts_test.wav"
TELUGU_TEST_TEXT = "మీ చెరువు నీటి విలువలను ఇప్పుడు కొలవండి."


def main() -> int:
    try:
        audio_bytes = synthesize_speech(TELUGU_TEST_TEXT)
        OUTPUT_FILE.parent.mkdir(exist_ok=True)
        OUTPUT_FILE.write_bytes(audio_bytes)
    except (GnaniTTSError, OSError) as exc:
        print(f"Gnani TTS test failed: {exc}")
        return 1

    print(f"Gnani TTS test succeeded: {OUTPUT_FILE} ({len(audio_bytes)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
