"""
scripts/seed_faces.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FR-8: One-time face enrollment script for the demo.

Captures N frames from the webcam, extracts face embeddings with
InsightFace, averages them for stability, and writes the resulting
user record to Firestore.

Run once per person BEFORE the demo (on the kiosk hardware):

    python scripts/seed_faces.py --name "Haseeb" --role student --interests AIML,robotics,computer_vision

Prerequisites:
  - pip install insightface onnxruntime firebase-admin
  - FIREBASE_CREDENTIALS_PATH env var pointing to service-account JSON
  - webcam available at index 0 (or set CAMERA_INDEX env var)
"""

import argparse
import os
import sys
import time
import uuid
import logging

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_faces")

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))


def parse_args():
    parser = argparse.ArgumentParser(description="Enroll a user's face into Firebase for FR-8.")
    parser.add_argument("--name", required=True, help="Full name of the person (e.g. 'Haseeb')")
    parser.add_argument(
        "--role",
        required=True,
        choices=["student", "professor", "guest"],
        help="User role for role-based access control (FR-7)",
    )
    parser.add_argument(
        "--interests",
        default="",
        help="Comma-separated interest tags for FR-10 recommendations (e.g. 'AIML,robotics')",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Custom user_id. Auto-generated if not provided.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=5,
        help="Number of frames to capture and average (default: 5)",
    )
    parser.add_argument(
        "--language",
        default="en",
        choices=["en", "kn", "hi"],
        help="Preferred language for greetings (default: en)",
    )
    return parser.parse_args()


def capture_embeddings(n_frames: int) -> list:
    """Capture N good face embeddings from the webcam and return as a list of arrays."""
    from detection.face_extractor import FaceExtractor

    extractor = FaceExtractor()

    camera_index = int(os.getenv("CAMERA_INDEX", "0"))
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        logger.error(f"Cannot open camera {camera_index}. Check CAMERA_INDEX env var.")
        sys.exit(1)

    print("\n>>> Camera opened. Look directly at the camera.")
    print(">>> Waiting for InsightFace model to load (may take ~10 seconds)...")

    # Wait for InsightFace to finish loading
    for _ in range(60):
        if extractor.is_ready:
            break
        time.sleep(0.5)
    else:
        logger.error("InsightFace did not load in time. Check installation.")
        cap.release()
        sys.exit(1)

    print(f">>> Model ready! Capturing {n_frames} frames. Hold still...")

    embeddings = []
    attempts = 0
    max_attempts = n_frames * 10  # Allow retries for missed frames

    while len(embeddings) < n_frames and attempts < max_attempts:
        ret, frame = cap.read()
        if not ret:
            logger.warning("Failed to read frame — retrying...")
            time.sleep(0.2)
            attempts += 1
            continue

        emb = extractor.extract(frame)
        if emb is not None:
            embeddings.append(emb)
            print(f"  ✓ Frame {len(embeddings)}/{n_frames} captured.")
        else:
            print("  ✗ No face in frame — please look at the camera.")

        attempts += 1
        time.sleep(0.3)

    cap.release()

    if len(embeddings) < n_frames:
        logger.error(
            f"Only captured {len(embeddings)}/{n_frames} embeddings. "
            "Ensure your face is clearly visible to the camera."
        )
        if not embeddings:
            sys.exit(1)

    return embeddings


def average_embedding(embeddings: list) -> list:
    """Average a list of embeddings and re-normalise."""
    arr = np.array(embeddings, dtype=np.float32)  # (N, 512)
    avg = arr.mean(axis=0)
    norm = np.linalg.norm(avg)
    return (avg / norm).tolist() if norm > 0 else avg.tolist()


def main():
    args = parse_args()

    name = args.name.strip()
    role = args.role
    interests = [i.strip() for i in args.interests.split(",") if i.strip()]
    user_id = args.user_id or f"usr_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    language = args.language

    print(f"\n{'='*55}")
    print(f"  FR-8 Face Enrollment: {name}")
    print(f"  Role      : {role}")
    print(f"  Interests : {interests or '(none)'}")
    print(f"  User ID   : {user_id}")
    print(f"{'='*55}\n")

    # Step 1: Capture embeddings
    embeddings = capture_embeddings(args.frames)
    final_embedding = average_embedding(embeddings)
    print(f"\n>>> Embedding ready (dim={len(final_embedding)}, averaged over {len(embeddings)} frames).")

    # Step 2: Write to Firebase
    print(">>> Saving to Firebase Firestore...")
    from backend.app.services.firebase_client import register_user

    success = register_user(
        user_id=user_id,
        name=name,
        role=role,
        face_embedding=final_embedding,
        interests=interests,
        language=language,
    )

    if success:
        print("\n✅ Enrollment complete!")
        print(f"   User ID  : {user_id}")
        print(f"   Name     : {name}")
        print(f"   Role     : {role}")
        print(f"   Interests: {interests}")
        print("\n   This user will now be recognised at the kiosk.")
    else:
        print("\n❌ Enrollment FAILED. Check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
