import asyncio
import json
import os
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from aquaguard.agent import root_agent
from aquaguard.water_agent import water_agent
from aquaguard.weather_agent import weather_agent
from aquaguard.market_agent import market_agent


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_FILE = PROJECT_ROOT / "data" / "farm_data.json"

APP_NAME = "aquaguard"
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


async def run_agent(agent, prompt: str, user_id: str) -> str:
    """Run one ADK agent and return its final text response."""
    session_service = InMemorySessionService()

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    runner = Runner(
        app_name=APP_NAME,
        agent=agent,
        session_service=session_service,
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    final_text = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response() and event.content:
            parts = event.content.parts or []

            text_parts = [
                part.text
                for part in parts
                if getattr(part, "text", None)
            ]

            if text_parts:
                final_text = "\n".join(text_parts)

    return final_text


async def main() -> None:
    if not os.getenv("GOOGLE_API_KEY"):
        raise EnvironmentError(
            "GOOGLE_API_KEY is not set in this PowerShell session."
        )

    farm_data = load_farm_data()
    farm_json = json.dumps(farm_data, indent=2)

    print("\n=== AquaGuard Farm Assessment ===\n")

    # ---------------------------------------------------------
    # 1. Water Quality Agent
    # ---------------------------------------------------------
    water_prompt = f"""
Analyze ONLY the water-quality portion of this structured farm dataset.

Structured farm data:
{farm_json}

Focus on:
- dissolved oxygen
- pH
- temperature
- salinity

Do not invent values.
Clearly distinguish observed values from inferences.
Return your normal structured Water Quality Agent response.
"""

    water_result = await run_agent(
        water_agent,
        water_prompt,
        f"{USER_ID}_water",
    )

    print("✓ Water Quality Agent completed")

    # ---------------------------------------------------------
    # 2. Weather Risk Agent
    # ---------------------------------------------------------
    weather_prompt = f"""
Analyze ONLY the weather/environment portion of this structured farm dataset.

Structured farm data:
{farm_json}

Focus on:
- rainfall
- temperature
- forecast information
- weather conditions

Do not invent missing weather information.
Clearly distinguish supplied observations from inferences.
Return your normal structured Weather Risk Agent response.
"""

    weather_result = await run_agent(
        weather_agent,
        weather_prompt,
        f"{USER_ID}_weather",
    )

    print("✓ Weather Risk Agent completed")

    # ---------------------------------------------------------
    # 3. Market Intelligence Agent
    # ---------------------------------------------------------
    market_prompt = f"""
Analyze ONLY the market portion of this structured farm dataset.

Structured farm data:
{farm_json}

Focus on:
- current market price
- price trend
- harvest economics
- timing considerations

Do not invent market information.
Clearly distinguish supplied information from inference.
Return your normal structured Market Intelligence Agent response.
"""

    market_result = await run_agent(
        market_agent,
        market_prompt,
        f"{USER_ID}_market",
    )

    print("✓ Market Intelligence Agent completed")

    # ---------------------------------------------------------
    # 4. Root Agent synthesizes all specialist findings
    # ---------------------------------------------------------
    synthesis_prompt = f"""
You are receiving completed findings from all three AquaGuard
specialist agents.

Do NOT invent new measurements or facts.
Do NOT claim that live sensors, live weather APIs, or live market
feeds were accessed.

Use ONLY the specialist findings below to produce the final
AquaGuard decision-support assessment.

=== WATER QUALITY AGENT ===
{water_result}

=== WEATHER RISK AGENT ===
{weather_result}

=== MARKET INTELLIGENCE AGENT ===
{market_result}

Now synthesize all three domains.

Your final response must use exactly:

Risk:
HIGH, MODERATE, LOW, or INSUFFICIENT DATA

Key evidence:

- Domain: concise evidence from that domain.
  Label supplied facts as "Observed:" and interpretations as
  "Inference:".

Recommended next step:
One practical, farmer-friendly next step supported by the evidence.

Why:
Explain how the environmental signals relate to the assessment.
Keep market context separate from biological/environmental risk.

Uncertainty / Missing information:
List only genuine limitations or missing information.

This is a prototype demonstration using structured farm data.
"""

    final_result = await run_agent(
        root_agent,
        synthesis_prompt,
        USER_ID,
    )

    print("\n=== AquaGuard Integrated Assessment ===\n")
    print(final_result)
    print("\n=== Assessment Complete ===\n")


if __name__ == "__main__":
    asyncio.run(main())