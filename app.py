from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pyrebase
import streamlit as st

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