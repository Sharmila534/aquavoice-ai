import asyncio
import json
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

APP_NAME = "aquaguard-workflow"
USER_ID = "demo_farmer"
conversation_sessions = InMemorySessionService()


def load_farm_data() -> dict:
    """Load the structured farm dataset."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Farm data file not found: {DATA_FILE}"
        )

    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "farm_data.json must contain a JSON object."
        )

    return data


async def run_agent(agent, prompt: str, user_id: str) -> str:
    """Run an ADK agent and return its final response."""
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


async def run_workflow() -> dict:
    farm_data = load_farm_data()
    farm_json = json.dumps(farm_data, indent=2)

    print("\n=== AquaGuard Multi-Agent Workflow ===\n")

    # ---------------------------------------------------------
    # 1. WATER QUALITY AGENT
    # ---------------------------------------------------------
    print("→ Running Water Quality Agent...")


    water_result = await run_agent(
        water_agent,
        f"""
Analyze the water-quality conditions in this aquaculture farm.

Use ONLY the supplied structured data.

Farm data:
{farm_json}

Focus on:
- dissolved oxygen
- pH
- temperature
- salinity

Do not invent measurements.
Clearly distinguish observations from inferences.
Return your normal Water Quality Agent assessment.
""",
        f"{USER_ID}_water",
    )

    print("✓ Water Quality Agent completed")

    # ---------------------------------------------------------
    # 2. WEATHER RISK AGENT
    # ---------------------------------------------------------
    print("\n→ Running Weather Risk Agent...")

    weather_result = await run_agent(
        weather_agent,
        f"""
Analyze the weather and environmental conditions in this aquaculture farm.

Use ONLY the supplied structured data.

Farm data:
{farm_json}

Focus on:
- rainfall
- temperature
- forecast information
- weather conditions

Do not invent weather information.
Clearly distinguish observations from inferences.
Return your normal Weather Risk Agent assessment.
""",
        f"{USER_ID}_weather",
    )

    print("✓ Weather Risk Agent completed")

    # ---------------------------------------------------------
    # 3. MARKET INTELLIGENCE AGENT
    # ---------------------------------------------------------
    print("\n→ Running Market Intelligence Agent...")

    market_result = await run_agent(
        market_agent,
        f"""
Analyze the market information in this aquaculture farm dataset.

Use ONLY the supplied structured data.

Farm data:
{farm_json}

Focus on:
- current market price
- price trend
- harvest economics
- timing considerations

Do not invent market values or trends.
Clearly distinguish observations from inferences.
Return your normal Market Intelligence Agent assessment.
""",
        f"{USER_ID}_market",
    )

    print("✓ Market Intelligence Agent completed")

    # ---------------------------------------------------------
    # 4. ROOT AGENT SYNTHESIS
    # ---------------------------------------------------------
    print("\n→ Root Agent synthesizing all specialist findings...")

    synthesis_prompt = f"""
You are AquaGuard AI, the Root Decision Agent.

Three specialist agents have completed their analyses.

Your job is to synthesize those analyses into one farmer-friendly
decision-support response.

IMPORTANT:
- Use only the supplied farm data and specialist outputs.
- Do not invent measurements, weather conditions, prices, or history.
- Do not claim access to live sensors or external APIs.
- Keep observations separate from inferences.
- Keep market context separate from environmental risk.
- Preserve uncertainty and missing information.

=== FARM DATA ===

{farm_json}

=== WATER QUALITY AGENT ===

{water_result}

=== WEATHER RISK AGENT ===

{weather_result}

=== MARKET INTELLIGENCE AGENT ===

{market_result}

Return exactly this structure:

Risk:
HIGH, MODERATE, LOW, or INSUFFICIENT DATA

Key evidence:

- Water Quality:
  Observed:
  Inference:

- Weather:
  Observed:
  Inference:

- Market:
  Observed:
  Inference:

Recommended next step:
<one practical action supported by the evidence>

Why:
<short evidence-based explanation>

Uncertainty / Missing information:
<genuine missing information and limitations>
"""

    final_result = await run_agent(
        root_agent,
        synthesis_prompt,
        f"{USER_ID}_root",
    )

    print("✓ Root Agent completed")

    print("\n=== FINAL AQUAGUARD DECISION ===\n")
    print(final_result)

    print("\n=== ORCHESTRATION COMPLETE ===\n")

    return {
        "farm_data": farm_data,
        "water_quality": water_result,
        "weather_risk": weather_result,
        "market_intelligence": market_result,
        "final_decision": final_result,
    }
async def ask_aquaguard(
    question: str,
    farm_data: dict,
    user_id: str,
    session_id: str | None = None,
) -> tuple[str, str]:
    """
    Run a true multi-turn AquaGuard conversation.

    The same ADK session is reused when session_id is provided.
    """
    if not question.strip():
        raise ValueError("Question cannot be empty.")

    if session_id is None:
        session = await conversation_sessions.create_session(
            app_name="aquaguard-chat",
            user_id=user_id,
        )
        session_id = session.id

    runner = Runner(
        app_name="aquaguard-chat",
        agent=root_agent,
        session_service=conversation_sessions,
    )

    farm_context = json.dumps(
        farm_data,
        indent=2,
    )

    prompt = f"""
You are AquaGuard AI assisting a farmer.

The authenticated farmer's current farm context is:

{farm_context}

Farmer's question:
{question}

Instructions:
- Answer the farmer's actual question directly.
- Use the supplied farm context when relevant.
- Preserve the conversation context from previous messages.
- Do not invent measurements, weather data, market data, or farm history.
- Distinguish facts from general guidance.
- If the question requires missing information, say what is missing.
- Keep the answer understandable to a farmer.
- Do not repeat the entire farm assessment unless it is necessary.
"""

    message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    response_parts = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if getattr(part, "text", None):
                    response_parts.append(part.text)

    answer = "\n".join(response_parts).strip()

    return answer, session_id

if __name__ == "__main__":
    asyncio.run(run_workflow())