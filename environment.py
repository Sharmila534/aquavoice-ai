"""Local environment loading for AquaGuard services.

Values already supplied by PowerShell, CI, or a deployment environment are
never overwritten by the local .env file.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent


def load_environment() -> None:
    """Load project-local development variables without replacing real env vars."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)

    # AquaGuard's existing ADK code reads GOOGLE_API_KEY. Keep that name as the
    # primary setting while accepting GEMINI_API_KEY as a local compatibility
    # alias when GOOGLE_API_KEY has not been supplied.
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


load_environment()
