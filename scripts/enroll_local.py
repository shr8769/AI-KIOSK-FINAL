"""
scripts/enroll_local.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FR-8: Local face enrollment — writes real embeddings directly
      to database/mock_firestore.json (no Firebase required).

Use this to finalize face embeddings for the Sprint 1 checkpoint.

Usage:
    cd "c:\\Users\\Harsh\\OneDrive\\Desktop\\PESU RF\\AI-KIOSK"
    python scripts/enroll_local.py --name "Harsha" --role student --interests "AIML,computer_vision,coding"
    python scripts/enroll_local.py --name "Haseeb" --role student --interests "AIML,robotics,software_engineering"
    python scripts/enroll_local.py --name "Gowtham" --role student --interests "data_science,machine_learning,AIML"

After enrollment, verify with:
    python scripts/enroll_local.py --verify
"""

import argparse
import json
import os
import sys
import time
import uuid
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enroll_local")

# ── Project root on path ───────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

MOCK_DB_PATH = os.path.join(ROOT, "database", "mock_firestore.json")
OPPS_PATH    = os.path.join(ROOT, "knowledge", "sources", "opportunities.json")


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_db() -> dict:
    if os.path.exists(MOCK_DB_PATH):
        with open(MOCK_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # Bootstrap from opportunities file
    opps = []
    if os.path.exists(OPPS_PATH):
        with open(OPPS_PATH, "r", encoding="utf-8") as f:
            opps = json.load(f)
    return {"users": {}, "opportunities": {o["opportunity_id"]: o for o in opps}}


def save_db(data: dict):
    os.makedirs(os.path.dirname(MOCK_DB_PATH), exist_ok=True)
    with open(MOCK_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info(f"Saved to {MOCK_DB_PATH}")


def capture_embeddings(n_frames: int, camera_index: int) -> list:
    """Capture N face embeddings from the webcam using InsightFace."""
    import cv2
    import numpy as np
    from detection.face_extractor import FaceExtractor

    extractor = FaceExtractor()

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.error(f"Cannot open camera {camera_index}. Check CAMERA_INDEX env var.")
        sys.exit(1)

    print(f"\n>>> Camera opened. Look directly at the camera.")
    print(f">>> Waiting for InsightFace model to load (~5-10 seconds)...")

    for _ in range(30):
        if extractor.is_ready:
            break
        time.sleep(0.5)
    else:
        logger.error("InsightFace did not load. Check: pip install insightface onnxruntime")
        cap.release()
        sys.exit(1)

    print(f">>> Model ready! Capturing {n_frames} frames — hold still and look at the camera...\n")

    # Show live preview window while capturing
    embeddings = []
    attempts = 0
    max_attempts = n_frames * 15

    while len(embeddings) < n_frames and attempts < max_attempts:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            attempts += 1
            continue

        # Show live feed with capture count overlay
        display = frame.copy()
        status = f"Captured {len(embeddings)}/{n_frames}"
        cv2.putText(display, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.imshow("Face Enrollment — Press Q to cancel", display)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Cancelled by user.")
            break

        emb = extractor.extract(frame)
        if emb is not None:
            embeddings.append(emb)
            print(f"  [OK] Frame {len(embeddings)}/{n_frames} captured.")
        else:
            print(f"  [!!] No face detected -- move closer to the camera.")

        attempts += 1
        time.sleep(0.3)

    cap.release()
    cv2.destroyAllWindows()

    if not embeddings:
        logger.error("No embeddings captured. Make sure your face is clearly visible.")
        sys.exit(1)

    return embeddings


def average_embedding(embeddings: list) -> list:
    """Average multiple embeddings and re-normalise for stability."""
    import numpy as np
    arr = np.array(embeddings, dtype=np.float32)
    avg = arr.mean(axis=0)
    norm = np.linalg.norm(avg)
    return (avg / norm).tolist() if norm > 0 else avg.tolist()


# ── Verify mode ────────────────────────────────────────────────────────────────

def verify_enrollment():
    """Quick sanity-check: show all enrolled users and their embedding stats."""
    import numpy as np

    data = load_db()
    users = data.get("users", {})

    if not users:
        print(f"  [!!] No users enrolled yet. Run with --name to enroll someone.")
        return

    print(f"\n{'='*60}")
    print(f"  Enrolled Users ({len(users)} total)")
    print(f"{'='*60}")
    for uid, u in users.items():
        emb = u.get("face_embedding", [])
        is_real = any(v != 0.1 and v != 0.0 and v != 1.0 for v in emb[:10])
        emb_type = "REAL InsightFace [OK]" if is_real else "[!!] DUMMY (needs re-enrollment)"
        print(f"\n  Name     : {u.get('name')}")
        print(f"  Role     : {u.get('role')}")
        print(f"  User ID  : {uid}")
        print(f"  Embedding: {emb_type} (dim={len(emb)})")
        print(f"  Interests: {u.get('preferences', {}).get('interests', [])}")

    print(f"\n{'='*60}")
    opps = data.get("opportunities", {})
    print(f"  Opportunities: {len(opps)} loaded")
    print(f"{'='*60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Enroll a face into mock_firestore.json for FR-8 local testing."
    )
    parser.add_argument("--name", help="Full name (e.g. 'Harsha')")
    parser.add_argument(
        "--role", choices=["student", "professor", "guest"], default="student"
    )
    parser.add_argument(
        "--interests", default="AIML",
        help="Comma-separated interest tags (e.g. 'AIML,robotics')"
    )
    parser.add_argument("--user-id", default=None, help="Custom user_id (auto-generated if omitted)")
    parser.add_argument("--frames", type=int, default=5, help="Frames to capture (default: 5)")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--verify", action="store_true", help="Show all enrolled users and exit")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verify:
        verify_enrollment()
        return

    if not args.name:
        print("Error: --name is required for enrollment. Use --verify to list current users.")
        sys.exit(1)

    name      = args.name.strip()
    role      = args.role
    interests = [i.strip() for i in args.interests.split(",") if i.strip()]
    user_id   = args.user_id or f"usr_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"

    print(f"\n{'='*55}")
    print(f"  FR-8 Local Face Enrollment")
    print(f"{'='*55}")
    print(f"  Name      : {name}")
    print(f"  Role      : {role}")
    print(f"  Interests : {interests}")
    print(f"  User ID   : {user_id}")
    print(f"  Camera    : {args.camera}")
    print(f"{'='*55}")

    # Capture
    raw_embeddings = capture_embeddings(args.frames, args.camera)
    final_embedding = average_embedding(raw_embeddings)

    print(f"\n>>> Embedding ready (dim={len(final_embedding)}, averaged over {len(raw_embeddings)} frames).")

    # Save to mock_firestore.json
    data = load_db()
    data.setdefault("users", {})[user_id] = {
        "user_id": user_id,
        "name": name,
        "role": role,
        "face_embedding": final_embedding,
        "preferences": {
            "interests": interests,
            "language": "en",
        },
    }
    save_db(data)

    print(f"\n[OK] Enrollment complete!")
    print(f"   {name} is now registered in mock_firestore.json")
    print(f"   The kiosk will greet them by name when they walk up.\n")
    print(f"   Run --verify to confirm all enrollments.")


if __name__ == "__main__":
    main()
