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

APP_NAME = "aquaguard-orchestration-demo"
USER_ID = "demo_farmer"


def load_farm_data() -> dict:
    """Load the structured farm dataset."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Farm data file not found: {DATA_FILE}")

    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("farm_data.json must contain a JSON object.")

    return data


def build_user_request(farm_data: dict) -> str:
    """Build a farmer-style request for the Root Agent."""
    return f"""
You are assessing one aquaculture farm using the supplied structured data.

The Root Agent must orchestrate the specialist agents as needed.

Structured farm data:
{json.dumps(farm_data, indent=2)}

Farmer question:

"Based on my current farm conditions, what is my overall environmental
risk, what evidence supports it, and what should I do next?"

Requirements:
- Use the Water Quality Agent for water-quality analysis.
- Use the Weather Risk Agent for weather/environment analysis.
- Use the Market Intelligence Agent for market context when relevant.
- Do not invent information.
- Do not claim live sensors, live weather APIs, or live market feeds.
- Preserve uncertainty.
- Return AquaGuard's required final format.
"""


async def main() -> None:
    if not os.getenv("GOOGLE_API_KEY"):
        raise EnvironmentError(
            "GOOGLE_API_KEY is not set in this PowerShell session."
        )

    farm_data = load_farm_data()
    user_request = build_user_request(farm_data)

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
        parts=[types.Part(text=user_request)],
    )

    print("\n=== AquaGuard Phase 4: Root-Agent Orchestration ===\n")
    print("Starting Root Agent...\n")

    seen_agents = []

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=message,
    ):
        author = getattr(event, "author", None)

        if author and author not in seen_agents:
            seen_agents.append(author)
            print(f"→ Agent activity: {author}")

        if event.is_final_response() and event.content:
            parts = event.content.parts or []

            text_parts = [
                part.text
                for part in parts
                if getattr(part, "text", None)
            ]

            if text_parts:
                print("\n=== FINAL AQUAGUARD DECISION ===\n")
                print("\n".join(text_parts))

    print("\n=== Orchestration Summary ===\n")

    if seen_agents:
        print("Agents observed during execution:")
        for agent_name in seen_agents:
            print(f"✓ {agent_name}")
    else:
        print("No agent event metadata was exposed by the runtime.")

    print("\n=== Phase 4 Demo Complete ===\n")


if __name__ == "__main__":
    asyncio.run(main())