"""
backend/app/services/firebase_client.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FR-8 + FR-10: Firebase Firestore client
Owner: Harsha

Provides two public APIs:
  - match_face(embedding)          → User dict | None        (FR-8)
  - get_recommendations(user_id)   → list[dict]              (FR-10)

Environment variables:
  FIREBASE_CREDENTIALS_PATH  — path to service-account JSON key
                               (default: firebase-credentials.json in CWD)
  FACE_MATCH_THRESHOLD       — cosine similarity cutoff (default: 0.85)

Graceful degradation:
  If Firebase cannot connect (missing credentials, network issue),
  all functions return None / [] and log a warning. The rest of
  the pipeline is completely unaffected.
"""

import json
import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy singleton ──────────────────────────────────────────────────────────
_db = None
_firebase_available = True  # Set to False after first failed init attempt


def _get_firestore():
    """Lazy-initialise the Firestore client (thread-safe for read)."""
    global _db, _firebase_available

    if _db is not None:
        return _db
    if not _firebase_available:
        return None

    try:
        import firebase_admin  # type: ignore
        from firebase_admin import credentials, firestore  # type: ignore

        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")

        if not firebase_admin._apps:
            if not os.path.exists(cred_path):
                logger.warning(
                    f"[Firebase] Credentials file not found at '{cred_path}'. "
                    "Set FIREBASE_CREDENTIALS_PATH env var. FR-8/FR-10 disabled."
                )
                _firebase_available = False
                return None
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        _db = firestore.client()
        logger.info("[Firebase] Firestore connected successfully.")
        return _db

    except ImportError:
        logger.warning(
            "[Firebase] firebase-admin not installed. "
            "Run: pip install firebase-admin. FR-8/FR-10 disabled."
        )
        _firebase_available = False
        return None
    except Exception as e:
        logger.error(f"[Firebase] Initialisation failed: {e}. FR-8/FR-10 disabled.")
        _firebase_available = False
        return None


# ── Local JSON-based Mock Fallback (when Firebase is offline) ───────────────


def _get_mock_db_path():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    return os.path.join(root, "database", "mock_firestore.json")


def _load_mock_db() -> dict:
    path = _get_mock_db_path()
    if not os.path.exists(path):
        # Auto-seed opportunities from local knowledge files if available
        opps = []
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        opps_src = os.path.join(root, "knowledge", "sources", "opportunities.json")
        if os.path.exists(opps_src):
            try:
                with open(opps_src, "r", encoding="utf-8") as f:
                    opps = json.load(f)
            except Exception:
                pass
        return {"users": {}, "opportunities": opps}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "opportunities": []}


def _save_mock_db(data: dict):
    path = _get_mock_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Mock Firebase] Failed to save mock DB: {e}")


# ── FR-8: Face Matching ────────────────────────────────────────────────────


def match_face(embedding: list, threshold: Optional[float] = None) -> Optional[dict]:
    """
    Find the closest matching user in the 'users' Firestore collection
    by cosine similarity against stored 512D face embeddings.

    Args:
        embedding:  L2-normalised 512D list[float] from FaceExtractor.
        threshold:  Minimum cosine similarity to accept a match.
                    Defaults to FACE_MATCH_THRESHOLD env var or 0.85.

    Returns:
        User dict { user_id, name, role, preferences, ... }
        or None if no match above threshold / Firebase unavailable.
    """
    if threshold is None:
        threshold = float(os.getenv("FACE_MATCH_THRESHOLD", "0.85"))

    db = _get_firestore()
    if db is None:
        logger.info(
            "[FR-8] Firebase disabled. Falling back to local mock_firestore.json matching..."
        )
        try:
            data = _load_mock_db()
            users = data.get("users", {})
            query_vec = np.array(embedding, dtype=np.float32)
            best_sim = -1.0
            best_user = None

            for user_id, user in users.items():
                stored_emb = user.get("face_embedding")
                if not stored_emb or len(stored_emb) != len(embedding):
                    continue
                stored_vec = np.array(stored_emb, dtype=np.float32)
                sim = float(np.dot(query_vec, stored_vec))
                if sim > best_sim:
                    best_sim = sim
                    best_user = user

            if best_user and best_sim >= threshold:
                logger.info(
                    f"[FR-8] [Mock] Face matched: name='{best_user.get('name')}' "
                    f"role='{best_user.get('role')}' sim={best_sim:.3f}"
                )
                return best_user
            logger.info(
                f"[FR-8] [Mock] No face match above threshold {threshold} (best_sim={best_sim:.3f})."
            )
            return None
        except Exception as e:
            logger.error(f"[FR-8] [Mock] Face matching failed: {e}")
            return None

    try:
        query_vec = np.array(embedding, dtype=np.float32)

        users_stream = db.collection("users").stream()

        best_sim: float = -1.0
        best_user: Optional[dict] = None

        for doc in users_stream:
            user = doc.to_dict()
            stored_emb = user.get("face_embedding")
            if not stored_emb or len(stored_emb) != len(embedding):
                continue

            stored_vec = np.array(stored_emb, dtype=np.float32)
            # Both embeddings are L2-normalised ⟹ dot product == cosine similarity.
            sim = float(np.dot(query_vec, stored_vec))

            if sim > best_sim:
                best_sim = sim
                best_user = user

        if best_user and best_sim >= threshold:
            logger.info(
                f"[FR-8] Face matched: name='{best_user.get('name')}' "
                f"role='{best_user.get('role')}' sim={best_sim:.3f}"
            )
            return best_user

        logger.info(
            f"[FR-8] No face match above threshold {threshold} "
            f"(best_sim={best_sim:.3f}). Treating as guest."
        )
        return None

    except Exception as e:
        logger.error(f"[FR-8] Face matching error: {e}")
        return None


# ── FR-10: Recommendations ────────────────────────────────────────────────


def get_recommendations(user_id: str, limit: int = 3) -> list:
    """
    Return the top N campus opportunities matching the user's interests.

    Matching logic:
      1. Load user's 'preferences.interests' list from Firestore.
      2. Query 'opportunities' collection for docs whose 'tags' array
         contains any of the user's interests (Firestore array_contains_any).
      3. Return up to `limit` results.

    Args:
        user_id:  Firestore document ID in the 'users' collection.
        limit:    Maximum number of recommendations to return.

    Returns:
        list of opportunity dicts, or [] if no match / Firebase unavailable.
    """
    db = _get_firestore()
    if db is None:
        logger.info(
            f"[FR-10] Firebase disabled. Fetching local mock recommendations for '{user_id}'..."
        )
        try:
            data = _load_mock_db()
            user = data.get("users", {}).get(user_id)
            if not user:
                logger.warning(f"[FR-10] [Mock] User '{user_id}' not found.")
                return []

            interests = user.get("preferences", {}).get("interests", [])
            if not interests:
                return []

            # Simple matching: check if any interest is in the tags
            interests_set = set(i.lower().strip() for i in interests)
            recs = []
            for opp in data.get("opportunities", []):
                opp_tags = [t.lower().strip() for t in opp.get("tags", [])]
                if any(tag in interests_set for tag in opp_tags):
                    recs.append(opp)
                    if len(recs) >= limit:
                        break
            logger.info(
                f"[FR-10] [Mock] Found {len(recs)} recommendation(s) for interests: {interests}"
            )
            return recs
        except Exception as e:
            logger.error(f"[FR-10] [Mock] Recommendation failed: {e}")
            return []

    try:
        # Step 1: Load user preferences
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            logger.warning(f"[FR-10] User '{user_id}' not found in Firestore.")
            return []

        user_data = user_doc.to_dict()
        interests: list = user_data.get("preferences", {}).get("interests", [])

        if not interests:
            logger.info(f"[FR-10] User '{user_id}' has no interests — no recommendations.")
            return []

        # Firestore array_contains_any supports up to 10 values
        interests_query = interests[:10]

        # Step 2: Query matching opportunities
        opps_query = (
            db.collection("opportunities")
            .where("tags", "array_contains_any", interests_query)
            .limit(limit)
        )

        results = [doc.to_dict() for doc in opps_query.stream()]
        logger.info(
            f"[FR-10] {len(results)} recommendation(s) for user '{user_id}' "
            f"(interests={interests_query})."
        )
        return results

    except Exception as e:
        logger.error(f"[FR-10] Recommendation fetch error for '{user_id}': {e}")
        return []


# ── FR-8: User Registration (used by seed_faces.py) ──────────────────────


def register_user(
    user_id: str,
    name: str,
    role: str,
    face_embedding: list,
    interests: Optional[list] = None,
    language: str = "en",
) -> bool:
    """
    Upsert a user record with face embedding in Firestore.
    Used by the one-time enrollment / seeding script.

    Returns True on success, False on failure.
    """
    db = _get_firestore()
    if db is None:
        logger.info(f"[Firebase] [Mock] Registering user '{name}' ({user_id}) locally...")
        try:
            data = _load_mock_db()
            data["users"][user_id] = {
                "user_id": user_id,
                "name": name,
                "role": role,
                "face_embedding": face_embedding,
                "preferences": {
                    "interests": interests or [],
                    "language": language,
                },
            }
            _save_mock_db(data)
            logger.info(f"[Firebase] [Mock] User '{name}' successfully registered locally.")
            return True
        except Exception as e:
            logger.error(f"[Firebase] [Mock] Failed to register user locally: {e}")
            return False

    try:
        from firebase_admin import firestore as fs  # type: ignore

        db.collection("users").document(user_id).set(
            {
                "user_id": user_id,
                "name": name,
                "role": role,
                "face_embedding": face_embedding,
                "preferences": {
                    "interests": interests or [],
                    "language": language,
                },
                "created_at": fs.SERVER_TIMESTAMP,
            },
            merge=True,  # Update existing doc if re-enrolling
        )
        logger.info(f"[Firebase] User '{name}' ({user_id}) registered successfully.")
        return True
    except Exception as e:
        logger.error(f"[Firebase] Failed to register user '{name}': {e}")
        return False
