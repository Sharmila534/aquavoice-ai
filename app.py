from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pyrebase
import streamlit as st

from aquavoice import LANGUAGE_NAMES, AquaVoiceInputError, respond_to_transcript
from gnani_stt import (
    GnaniConfigurationError,
    GnaniInputError,
    GnaniServiceError,
    SUPPORTED_AUDIO_TYPES,
    transcribe_audio,
)
from gnani_tts import (
    GnaniTTSConfigurationError,
    GnaniTTSInputError,
    GnaniTTSServiceError,
    synthesize_speech,
)
from security import get_firestore, verify_firebase_token
from workflow import ask_aquaguard, run_workflow


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_FILE = PROJECT_ROOT / "data" / "farm_data.json"


st.set_page_config(
    page_title="AquaGuard AI",
    page_icon="🌊",
    layout="wide",
)


# ============================================================
# Firebase Client
# ============================================================

firebase_config = {
    "apiKey": st.secrets["firebase"]["api_key"],
    "authDomain": st.secrets["firebase"]["auth_domain"],
    "projectId": st.secrets["firebase"]["project_id"],
    "storageBucket": st.secrets["firebase"]["storage_bucket"],
    "messagingSenderId": st.secrets["firebase"]["messaging_sender_id"],
    "appId": st.secrets["firebase"]["app_id"],
    "databaseURL": st.secrets["firebase"]["database_url"],
}

firebase = pyrebase.initialize_app(firebase_config)
firebase_auth = firebase.auth()


# ============================================================
# Session State
# ============================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "user" not in st.session_state:
    st.session_state.user = None

if "uid" not in st.session_state:
    st.session_state.uid = None

if "assessment" not in st.session_state:
    st.session_state.assessment = None

if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "aquavoice_session_id" not in st.session_state:
    st.session_state.aquavoice_session_id = None

if "aquavoice_live_answer" not in st.session_state:
    st.session_state.aquavoice_live_answer = None

if "aquavoice_manual_answer" not in st.session_state:
    st.session_state.aquavoice_manual_answer = None

# ============================================================
# Helper Functions
# ============================================================

def login_user(email: str, password: str) -> bool:
    """Authenticate the user with Firebase and verify the ID token."""
    try:
        user = firebase_auth.sign_in_with_email_and_password(
            email,
            password,
        )

        id_token = user["idToken"]

        # Verify token on the backend.
        decoded_token = verify_firebase_token(id_token)

        st.session_state.authenticated = True
        st.session_state.user = user
        st.session_state.uid = decoded_token["uid"]

        return True

    except Exception as exc:
        st.error(f"Login failed: {exc}")
        return False


def logout_user() -> None:
    """Clear the authenticated session."""
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.uid = None
    st.session_state.assessment = None
    st.session_state.chat_session_id = None
    st.session_state.chat_messages = []
    st.session_state.aquavoice_session_id = None
    st.session_state.aquavoice_live_answer = None
    st.session_state.aquavoice_manual_answer = None


def _write_uploaded_audio(uploaded_file) -> Path:
    """Place one Streamlit upload in a temporary file for the Gnani client."""

    suffix = Path(uploaded_file.name).suffix.lower()
    with NamedTemporaryFile(
        mode="wb", suffix=suffix, prefix="aquaguard_voice_", delete=False
    ) as temporary_file:
        temporary_file.write(uploaded_file.getbuffer())
        return Path(temporary_file.name)


def _provider_language(response: object) -> str | None:
    """Use a language only when Gnani explicitly includes a supported code."""

    if not isinstance(response, dict):
        return None

    for field_name in (
        "detected_language_code",
        "detected_language",
        "language_code",
    ):
        value = response.get(field_name)
        if value in LANGUAGE_NAMES:
            return value
    return None


def _is_cloudflare_1010(error: Exception) -> bool:
    message = str(error).lower()
    return "http 403" in message and (
        "1010" in message or "browser_signature_banned" in message
    )


def _is_gemini_unavailable(error: Exception) -> bool:
    message = str(error).upper()
    return "503" in message or "UNAVAILABLE" in message


def _aquavoice_stored_context(farm_data: dict) -> dict:
    """Attach provenance without changing the stored farm record itself."""

    context = dict(farm_data)
    water_quality = context.get("water_quality")
    water_quality = water_quality if isinstance(water_quality, dict) else {}

    context["_aquavoice_context_provenance"] = {
        "record_type": "stored farm record; not live telemetry",
        "storage_source": "authenticated user's FARM001 record supplied by the app",
        "prototype_note": (
            "The prototype can seed an absent FARM001 record from "
            "data/farm_data.json. Do not treat this record as a live reading."
        ),
        "water_record_observation_time": water_quality.get("observation_time"),
        "water_measurement_source": water_quality.get("source", "not provided"),
        "current_event_water_measurements": "not provided by the AquaVoice transcript",
    }
    return context


def _store_aquavoice_answer(state_key: str, answer: str, language_code: str) -> None:
    """Store one answer and discard audio generated for any older answer."""

    st.session_state[state_key] = {
        "text": answer,
        "language_code": language_code,
        "audio_bytes": None,
    }


def _render_telugu_tts(answer_state: dict | None, *, key_prefix: str) -> None:
    """Render one explicit, cached Timbre playback action for a Telugu answer."""

    if not answer_state or answer_state.get("language_code") != "te-IN":
        return

    answer_text = answer_state.get("text")
    if not isinstance(answer_text, str) or not answer_text.strip():
        return

    if st.button("Play answer in Telugu", key=f"{key_prefix}_play_telugu"):
        try:
            with st.spinner("Generating AI speech with Gnani Timbre..."):
                answer_state["audio_bytes"] = synthesize_speech(answer_text)
        except (GnaniTTSConfigurationError, GnaniTTSInputError) as exc:
            st.error(str(exc))
        except GnaniTTSServiceError:
            st.error("Gnani Timbre could not generate speech right now. No retry was attempted.")

    audio_bytes = answer_state.get("audio_bytes")
    if isinstance(audio_bytes, bytes):
        st.caption("AI-generated speech using Gnani Timbre.")
        st.audio(audio_bytes, format="audio/wav")


def load_local_demo_data() -> dict:
    """Load the current structured demo dataset."""
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_user_farm() -> dict:
    """
    Load FARM001 from the authenticated user's own Firestore path.

    For the prototype, initialize/repair the user's farm document
    from the structured demo dataset if the expected schema is missing.
    """
    if not st.session_state.uid:
        raise RuntimeError("Authenticated UID is missing.")

    db = get_firestore()
    uid = st.session_state.uid

    farm_ref = (
        db.collection("users")
        .document(uid)
        .collection("farms")
        .document("FARM001")
    )

    snapshot = farm_ref.get()

    if snapshot.exists:
        farm = snapshot.to_dict() or {}

        # Ensure the prototype farm has the expected nested data structure.
        required_sections = {
            "water_quality",
            "weather",
            "market",
        }

        if required_sections.issubset(farm.keys()):
            farm["farm_id"] = snapshot.id
            return farm

    # First-time initialization or schema repair for this user's farm.
    farm = load_local_demo_data()
    farm["farm_id"] = "FARM001"
    farm["owner_uid"] = uid

    farm_ref.set(farm, merge=True)

    return farm

def run_assessment():
    return asyncio.run(run_workflow())


# ============================================================
# LOGIN PAGE
# ============================================================

if not st.session_state.authenticated:

    st.title("🌊 AquaGuard AI")

    st.caption(
        "Multi-agent decision support for coastal aquaculture"
    )

    st.subheader("Farmer Login")

    with st.form("login_form"):
        email = st.text_input(
            "Email",
            placeholder="farmer@example.com",
        )

        password = st.text_input(
            "Password",
            type="password",
        )

        submitted = st.form_submit_button(
            "Sign in",
            type="primary",
        )

    if submitted:
        if not email or not password:
            st.warning("Please enter both email and password.")
        else:
            if login_user(email, password):
                st.success("Signed in successfully.")
                st.rerun()

    st.divider()

    st.caption(
        "Demo authentication uses Firebase Authentication."
    )

    st.stop()


# ============================================================
# AUTHENTICATED USER
# ============================================================

user = st.session_state.user
uid = st.session_state.uid

with st.sidebar:

    st.header("Farmer")

    st.write(
        f"**Account:** {user.get('email', 'Unknown')}"
    )

    st.write(
        f"**UID:** `{uid}`"
    )

    if st.button("Sign out"):
        logout_user()
        st.rerun()

    st.divider()


# ============================================================
# FARM DATA
# ============================================================

farm_data = load_user_farm()

# For the first prototype, fall back to the existing local demo
# dataset if FARM001 has not yet been loaded from Firestore.
if farm_data is None:
    farm_data = load_local_demo_data()

    st.info(
        "Using the prototype farm dataset. "
        "Authenticated Firestore storage is enabled for this user."
    )


# ============================================================
# SIDEBAR FARM INFORMATION
# ============================================================

with st.sidebar:

    st.header("Farm")

    st.write(
        f"**Farm ID:** {farm_data.get('farm_id', 'Unknown')}"
    )

    st.write(
        f"**Species:** {farm_data.get('species', 'Unknown')}"
    )

    st.write(
        f"**Stage:** {farm_data.get('production_stage', 'Unknown')}"
    )

    st.divider()

    st.subheader("Current Conditions")

    water = farm_data.get("water_quality", {})

    dissolved_oxygen = water.get("dissolved_oxygen", {})
    temperature = water.get("temperature", {})
    ph = water.get("ph", {})
    salinity = water.get("salinity", {})

    st.metric(
        "Dissolved Oxygen",
        f'{dissolved_oxygen.get("value", "N/A")} '
        f'{dissolved_oxygen.get("unit", "")}',
    )

    st.metric(
        "Temperature",
        f'{temperature.get("value", "N/A")}°C',
    )

    st.metric(
        "pH",
        f'{ph.get("value", "N/A")}',
    )

    st.metric(
        "Salinity",
        f'{salinity.get("value", "N/A")} ppt',
    )


# ============================================================
# MAIN DASHBOARD
# ============================================================

st.title("🌊 AquaGuard AI")

st.caption(
    "Multi-agent decision support for coastal aquaculture"
)

st.subheader("Farm Risk Assessment")

if st.button(
    "Run AquaGuard Assessment",
    type="primary",
):
    with st.spinner(
        "AquaGuard is analyzing water, weather and market conditions..."
    ):
        try:
            result = run_assessment()
            st.session_state.assessment = result

            # Store a lightweight assessment record under
            # the authenticated user's Firestore path.
            try:
                db = get_firestore()

                db.collection("users") \
                    .document(uid) \
                    .collection("assessments") \
                    .add({
                        "farm_id": farm_data.get("farm_id", "FARM001"),
                        "risk": "MODERATE",
                        "source": "AquaGuard prototype",
                    })

            except Exception as firestore_error:
                st.warning(
                    f"Assessment generated, but Firestore save failed: "
                    f"{firestore_error}"
                )

        except Exception as exc:
            st.error(
                "AquaGuard could not complete the assessment. "
                "Please try again later."
            )
            st.caption(str(exc))


if st.session_state.assessment:

    result = st.session_state.assessment

    final_decision = result["final_decision"]

    st.markdown("### AquaGuard Recommendation")

    st.info(final_decision)

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 💧 Water Agent")
        st.write(result["water_quality"])

    with col2:
        st.markdown("### 🌦️ Weather Agent")
        st.write(result["weather_risk"])

    with col3:
        st.markdown("### 📈 Market Agent")
        st.write(result["market_intelligence"])


# ============================================================
# AQUAVOICE
# ============================================================

st.divider()

st.subheader("AquaVoice")
st.caption(
    "Upload a short voice note for Gnani transcription, then receive an "
    "AquaGuard recommendation. Gnani live transcription is currently subject "
    "to a provider-side availability issue."
)

language_choices = {name: code for code, name in LANGUAGE_NAMES.items()}
selected_language_name = st.selectbox(
    "Answer language if Gnani does not return a detected language",
    options=list(language_choices),
    key="aquavoice_answer_language",
    help=(
        "This is your answer-language choice. It is not presented as Gnani "
        "language detection."
    ),
)
selected_language_code = language_choices[selected_language_name]

uploaded_audio = st.file_uploader(
    "Upload audio (maximum 30 seconds)",
    type=[extension.lstrip(".") for extension in SUPPORTED_AUDIO_TYPES],
    key="aquavoice_audio",
    help="Supported: WAV, MP3, OGG, FLAC, AAC, and M4A.",
)

duration_seconds = None
if uploaded_audio and Path(uploaded_audio.name).suffix.lower() != ".wav":
    duration_seconds = st.text_input(
        "Verified audio duration in seconds",
        value="",
        key="aquavoice_duration",
        help=(
            "Required for compressed uploads because AquaGuard does not guess "
            "audio duration. Enter a value no greater than 30."
        ),
    ) or None

if st.button("Transcribe uploaded audio with Gnani", key="aquavoice_transcribe"):
    if not uploaded_audio:
        st.warning("Upload an audio file before starting transcription.")
    else:
        temporary_audio = None
        try:
            temporary_audio = _write_uploaded_audio(uploaded_audio)
            with st.spinner("Sending one transcription request to Gnani..."):
                provider_response = transcribe_audio(
                    temporary_audio,
                    language_code="indic-auto",
                    duration_seconds=duration_seconds,
                )

            # Gnani's public REST example documents `transcript`. Do not guess
            # an alternative field or fabricate a transcription.
            transcript = (
                provider_response.get("transcript")
                if isinstance(provider_response, dict)
                else None
            )
            if not isinstance(transcript, str) or not transcript.strip():
                st.error(
                    "Gnani returned a successful response without a usable "
                    "transcript. AquaGuard did not generate an answer."
                )
            else:
                detected_language = _provider_language(provider_response)
                answer_language = detected_language or selected_language_code

                st.markdown("**Gnani transcript (live provider result)**")
                st.write(transcript)
                if detected_language:
                    st.caption(
                        f"Gnani-reported language: {LANGUAGE_NAMES[detected_language]} "
                        f"({detected_language})"
                    )
                else:
                    st.caption(
                        "Gnani did not return a supported detected-language code. "
                        f"Using your selected answer language: {selected_language_name} "
                        f"({selected_language_code})."
                    )

                with st.spinner("AquaGuard is preparing a recommendation..."):
                    answer, session_id = asyncio.run(
                        respond_to_transcript(
                            transcript=transcript,
                            detected_language=answer_language,
                            pond_information=_aquavoice_stored_context(farm_data),
                            user_id=uid,
                            session_id=st.session_state.aquavoice_session_id,
                        )
                    )
                st.session_state.aquavoice_session_id = session_id
                _store_aquavoice_answer(
                    "aquavoice_live_answer", answer, answer_language
                )
                st.markdown("**AquaGuard answer**")
                st.markdown(answer)

        except GnaniServiceError as exc:
            if _is_cloudflare_1010(exc):
                st.error(
                    "Gnani Prisma transcription is temporarily unavailable: "
                    "the provider's Cloudflare protection rejected this request "
                    "(HTTP 403 / Error 1010). No retry was attempted."
                )
            else:
                st.error("Gnani could not transcribe this audio. No retry was attempted.")
        except (GnaniInputError, GnaniConfigurationError) as exc:
            st.error(str(exc))
        except AquaVoiceInputError as exc:
            st.error(f"AquaVoice could not prepare this transcript: {exc}")
        except Exception as exc:
            if _is_gemini_unavailable(exc):
                st.error(
                    "Gemini is temporarily unavailable (HTTP 503). "
                    "Please try again later."
                )
            else:
                st.error("AquaVoice could not complete the recommendation right now.")
        finally:
            if temporary_audio is not None:
                temporary_audio.unlink(missing_ok=True)

with st.expander("Manual transcript test (Gemini handoff only)"):
    st.caption(
        "This sends manually entered text to AquaGuard. It is a Gemini handoff "
        "test, not a Gnani transcription."
    )
    manual_transcript = st.text_area(
        "Enter a farmer question or transcript",
        key="aquavoice_manual_transcript",
        placeholder="ఉదాహరణ: నా చెరువు నీటి నాణ్యత ఎలా ఉంది?",
    )
    manual_language_name = st.selectbox(
        "Language of the manually entered text",
        options=list(language_choices),
        key="aquavoice_manual_language",
    )
    if st.button("Test manual transcript with AquaGuard", key="aquavoice_manual_submit"):
        try:
            with st.spinner("AquaGuard is preparing a recommendation..."):
                answer, session_id = asyncio.run(
                    respond_to_transcript(
                        transcript=manual_transcript,
                        detected_language=language_choices[manual_language_name],
                        pond_information=_aquavoice_stored_context(farm_data),
                        user_id=uid,
                        session_id=st.session_state.aquavoice_session_id,
                    )
                )
            st.session_state.aquavoice_session_id = session_id
            _store_aquavoice_answer(
                "aquavoice_manual_answer",
                answer,
                language_choices[manual_language_name],
            )
            st.markdown("**Manual test transcript (not Gnani output)**")
            st.write(manual_transcript.strip())
            st.markdown("**AquaGuard answer**")
            st.markdown(answer)
        except AquaVoiceInputError as exc:
            st.error(f"Enter a valid transcript: {exc}")
        except Exception as exc:
            if _is_gemini_unavailable(exc):
                st.error(
                    "Gemini is temporarily unavailable (HTTP 503). "
                    "Please try again later."
                )
            else:
                st.error("AquaGuard could not complete the manual test right now.")


_render_telugu_tts(
    st.session_state.aquavoice_live_answer,
    key_prefix="aquavoice_live",
)
_render_telugu_tts(
    st.session_state.aquavoice_manual_answer,
    key_prefix="aquavoice_manual",
)


# ============================================================
# FARMER CHAT
# ============================================================

st.divider()

st.subheader("Ask AquaGuard")

st.caption(
    "Ask questions about your farm using AquaGuard's current farm context."
)

# Display previous conversation messages.
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


question = st.chat_input(
    "Example: What is my ideal temperature?"
)

if question:

    st.session_state.chat_messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):

        with st.spinner("AquaGuard is thinking..."):

            try:
                answer, session_id = asyncio.run(
                    ask_aquaguard(
                        question=question,
                        farm_data=farm_data,
                        user_id=uid,
                        session_id=st.session_state.chat_session_id,
                    )
                )

                st.session_state.chat_session_id = session_id

                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

                st.markdown(answer)

            except Exception as exc:

                error_message = (
                    "AquaGuard could not process your question right now."
                )

                st.error(error_message)

                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": error_message,
                    }
                )
