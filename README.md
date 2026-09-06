# AquaGuard AI

AquaGuard AI is a minimal four-agent decision-support architecture for coastal aquaculture. It analyzes only information supplied in a prompt. It does not connect to IoT devices, weather services, market feeds, Firebase, Firestore, Secret Manager, BigQuery MCP, or external APIs.

## Agent architecture

- `aquaguard/agent.py` defines `root_agent`, the AquaGuard coordinator.
- `aquaguard/water_agent.py` defines `water_agent`, which examines dissolved oxygen, pH, temperature, and salinity.
- `aquaguard/weather_agent.py` defines `weather_agent`, which examines rainfall, temperature, conditions, and forecast context.
- `aquaguard/market_agent.py` defines `market_agent`, which examines current price, price trend, harvest economics, and timing.
- `aquaguard/__init__.py` imports the agent module so the package follows the ADK entry-point convention.

The root agent uses Google ADK's `sub_agents` pattern to delegate relevant analysis to the three specialists. It then produces the farmer-facing response from the available evidence. Outputs are decision support, not guarantees.

## Local verification (Windows PowerShell / VS Code)

Run these commands in the VS Code PowerShell terminal from the project directory:

```powershell
Set-Location "C:\Users\saish\Desktop\AquaGuard"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The project intentionally pins:

```text
google-adk==2.4.*
mcp==1.29.*
```

Verify the package and root agent import before launching the UI:

```powershell
python -c "from importlib.metadata import version; import aquaguard; from aquaguard.agent import root_agent; print(root_agent.name); print(version('google-adk')); print(version('mcp'))"
```

Expected output includes `aquaguard`, a `google-adk` 2.4.x version, and an MCP 1.29.x version.

### Configure Gemini

This project currently uses the Gemini API-key configuration pattern:

```powershell
$env:GOOGLE_API_KEY = "your-api-key"
$env:GEMINI_MODEL = "gemini-2.5-flash"
```

The environment variables apply only to the current PowerShell session. Do not commit keys to source control.

### Launch ADK Web

With the virtual environment active and from `C:\Users\saish\Desktop\AquaGuard`, run:

```powershell
adk web . --host 127.0.0.1 --port 8000
```

`adk web` is provided by the installed `google-adk 2.4.x` CLI. The `.` argument tells ADK to discover agent packages below the current project directory; AquaGuard's entry point is `aquaguard.agent.root_agent`.

Open the local URL shown by the command, normally `http://127.0.0.1:8000`, then select AquaGuard.

### Representative local test prompt

Use supplied test data only; this is an illustrative local prompt, not live farm data:

```text
Assess today's farm decision using only this information.

Farm ID: demo-pond-01
Species: shrimp
Production stage: grow-out
Location: supplied coastal farm location
Water observation time: 2026-09-02 08:00
Dissolved oxygen: 4.2 mg/L
pH: 7.8
Water temperature: 30 C
Salinity: 20 ppt
Supplied farm dissolved-oxygen reference range: 5.0-7.0 mg/L, established by the farm operating plan.

Weather observation time: 2026-09-02 08:00
Forecast horizon: next 24 hours
Weather source: farmer-supplied local forecast summary
Forecast: heavy rainfall expected within 24 hours.

Market observation time: 2026-09-02
Product: shrimp
Market location: supplied local market
Current price: 420 INR/kg
Trend: farmer reports prices have been stable this week.
Market source: farmer-supplied market note.
```

The root response should be concise and use this structure:

```text
Risk:
HIGH / MODERATE / LOW / INSUFFICIENT DATA

Key evidence:
- Water Quality: Observed: ... Inference: ...
- Weather: Observed: ... Inference: ...
- Market: Observed: ... Inference: ...

Recommended next step:
...

Why:
...

Uncertainty / Missing information:
...
```

Only actually analyzed domains should appear. The response must keep environmental risk separate from market context, preserve missing information, avoid invented values, and avoid guarantees.

### Troubleshooting

**Python or virtual environment is missing**

- Confirm Python is available with `py --version`.
- Create the environment again with `py -3.12 -m venv .venv`.
- If PowerShell blocks activation, use either:

  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1
  ```

  or run `.venv\Scripts\python.exe` directly instead of activating it.

**`google-adk` or `adk` is missing**

- Ensure the virtual environment is active, then run:

  ```powershell
  python -m pip install -r requirements.txt
  python -m pip show google-adk mcp
  ```

- Verify the CLI with `adk web --help`.

**Gemini authentication fails**

- Set `GOOGLE_API_KEY` in the same PowerShell session that starts `adk web`.
- Check that the key is valid for the configured Gemini model.
- Do not mix this API-key setup with an unconfigured Vertex AI setup. If you intentionally move to Vertex AI later, update the project configuration first rather than adding unrelated environment variables.

**Incorrect project configuration**

- Run `adk web .` from `C:\Users\saish\Desktop\AquaGuard`, not from inside the `aquaguard` package.
- Confirm `aquaguard\agent.py` exports `root_agent`.
- Confirm the selected Python interpreter in VS Code is `C:\Users\saish\Desktop\AquaGuard\.venv\Scripts\python.exe`.
- Run the import check above before opening ADK Web.

## Future BigQuery MCP ownership architecture (documentation only)

BigQuery MCP is not implemented in this project yet. When it is introduced, data ownership and tool access must remain domain-scoped and read-only.

| Agent | Future data ownership | Allowed responsibility |
|---|---|---|
| Water Quality Agent | Farm water observations | Read only water measurements, supplied reference ranges, and water-quality history relevant to its assessment. |
| Weather Risk Agent | Relevant weather and forecast datasets | Read only weather observations and forecast context relevant to the farm/location/time under analysis. |
| Market Intelligence Agent | Market observations | Read only product, price, trend, market, and harvest-economics observations relevant to the request. |
| Root Agent | Coordination and synthesis | Route a request to domain specialists and synthesize their evidence. It must not become a generic unrestricted SQL or database agent. |

Future MCP controls:

- Expose a separate, least-privilege read-only toolset to each specialist; do not give specialists cross-domain datasets unless a documented use case requires it.
- Allow only read operations. Do not permit write SQL, DML, DDL, unrestricted database modification, or schema-changing commands.
- Keep the Root Agent away from direct database tools. It should receive specialist findings, domain-scoped evidence, and uncertainty rather than raw unrestricted query capability.
- Restrict each tool to allow-listed datasets, tables, views, and query patterns appropriate to its domain.
- Preserve an audit trail for every evidence-backed response: consulted domain, data source/dataset, query or tool identity, observation time when available, and the specialist that supplied the evidence.
- Keep Water, Weather, and Market evidence distinct in root synthesis. Cross-domain access should be exceptional, justified, documented, and minimized.
