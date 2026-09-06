from __future__ import annotations

import firebase_admin
from firebase_admin import auth, firestore


def initialize_firebase() -> None:
    """Initialize Firebase Admin using Google Application Default Credentials."""
    if not firebase_admin._apps:
        firebase_admin.initialize_app()


def get_firestore():
    """Return the Firestore client."""
    initialize_firebase()
    return firestore.client()


def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase Authentication ID token."""
    initialize_firebase()

    if not id_token:
        raise ValueError("Firebase ID token is required.")

    decoded_token = auth.verify_id_token(
        id_token,
        check_revoked=True,
    )

    uid = decoded_token.get("uid")

    if not uid:
        raise ValueError("Verified token does not contain a UID.")

    return decoded_token


def get_user_ref(db, uid: str):
    """Return the authenticated user's document."""
    if not uid:
        raise ValueError("UID is required.")

    return db.collection("users").document(uid)


def get_farm_ref(db, uid: str, farm_id: str):
    """Return a farm belonging only to the authenticated user."""
    if not uid:
        raise ValueError("UID is required.")

    if not farm_id:
        raise ValueError("Farm ID is required.")

    return (
        db.collection("users")
        .document(uid)
        .collection("farms")
        .document(farm_id)
    )


def get_assessment_ref(db, uid: str, assessment_id: str):
    """Return an assessment belonging only to the authenticated user."""
    if not uid:
        raise ValueError("UID is required.")

    if not assessment_id:
        raise ValueError("Assessment ID is required.")

    return (
        db.collection("users")
        .document(uid)
        .collection("assessments")
        .document(assessment_id)
    )