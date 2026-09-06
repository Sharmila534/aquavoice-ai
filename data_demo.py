import asyncio
import json
import os
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from aquaguard.agent import root_agent


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_FILE = PROJECT_ROOT / "data" / "farm_data.json"

APP_NAME = "aquaguard"
USER_ID = "demo_farmer"


def load_farm_data() -> dict:
    """Load structured farm data from the local JSON data layer."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Farm data file not found: {DATA_FILE}")

    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("farm_data.json must contain a JSON object.")

    return data


def build_prompt(farm_data: dict) -> str:
    """Convert structured farm data into a clear agent request."""
    return f"""
Assess the current farm situation using ONLY the structured farm data below.

This is a prototype demonstration using structured demo data.
Do not claim access to live sensors, live weather services, or live market feeds.

Structured farm data:
{json.dumps(farm_data, indent=2)}

Task:
1. Analyze the farm's water-quality information.
2. Analyze the supplied weather information.
3. Analyze the supplied market information.
4. Combine the specialist findings.
5. Return AquaGuard's final risk assessment and recommended next step.

Remember:
- Do not invent missing information.
- Preserve uncertainty.
- Keep environmental risk separate from market context.
- Treat the supplied values as observations from the demo dataset.
"""


async def main() -> None:
    if not os.getenv("GOOGLE_API_KEY"):
        raise EnvironmentError(
            "GOOGLE_API_KEY is not set. "
            "Set it in this PowerShell session before running the demo."
        )

    farm_data = load_farm_data()
    prompt = build_prompt(farm_data)

    session_service = InMemorySessionService()

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )

    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=session_service,
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    print("\n=== AquaGuard Phase 3 Data-Layer Demo ===\n")

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if getattr(part, "text", None):
                    print(part.text)

    print("\n=== End of Demo ===")


if __name__ == "__main__":
    asyncio.run(main())