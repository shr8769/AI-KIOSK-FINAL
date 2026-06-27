# FR-8 & FR-10: Firebase Setup Guide

## Step 1 — Create the Firebase Project (5 minutes)

1. Go to [https://console.firebase.google.com](https://console.firebase.google.com)
2. Click **Add project** → name it `vidyasahayak-kiosk`
3. Disable Google Analytics (not needed) → **Create project**
4. In the left sidebar: **Build → Firestore Database**
5. Click **Create database** → choose **Production mode** → select `asia-south1` (Mumbai) region
6. Click **Enable**

---

## Step 2 — Download Service Account Credentials

1. Go to **Project Settings** (gear icon) → **Service accounts**
2. Click **Generate new private key** → **Generate key**
3. Save the downloaded JSON file as:

```
AI-KIOSK/firebase-credentials.json
```

> ⚠️ **This file is in `.gitignore`. Never commit it.**

Set the env var in your `.env` file:
```env
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
FACE_MATCH_THRESHOLD=0.85
```

---

## Step 3 — Seed the Opportunities Collection (one-time)

Run this Python script to populate the `opportunities` collection from our local JSON:

```powershell
cd "c:\Users\Harsh\OneDrive\Desktop\PESU RF\AI-KIOSK"
python - << 'EOF'
import firebase_admin
from firebase_admin import credentials, firestore
import json, os

cred = credentials.Certificate("firebase-credentials.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

with open("knowledge/sources/opportunities.json") as f:
    opps = json.load(f)

batch = db.batch()
for opp in opps:
    ref = db.collection("opportunities").document(opp["opportunity_id"])
    batch.set(ref, opp)
batch.commit()
print(f"✅ Seeded {len(opps)} opportunities to Firestore.")
EOF
```

---

## Step 4 — Install Dependencies

```powershell
# Backend (Firebase client)
pip install firebase-admin==6.5.0

# Detection (InsightFace — CPU-only)
pip install insightface>=0.7.3 onnxruntime>=1.18.1
```

> If `onnxruntime` wheel fails on the kiosk ARM board, use:
> ```
> pip install onnxruntime-openvino  # Intel OpenVINO accelerated
> ```

---

## Step 5 — Enroll Team Member Faces (before July 10 demo)

Run once per person **on the kiosk hardware** (camera must be connected):

```powershell
# Enroll Haseeb as student interested in AIML and robotics
python scripts/seed_faces.py --name "Haseeb" --role student --interests "AIML,robotics,computer_vision"

# Enroll Harsha as student
python scripts/seed_faces.py --name "Harsha" --role student --interests "software_engineering,AIML,coding"

# Enroll Gowtham as student
python scripts/seed_faces.py --name "Gowtham" --role student --interests "data_science,AIML,machine_learning"

# Enroll a demo professor
python scripts/seed_faces.py --name "Prof. Demo" --role professor --interests "research,NLP,AIML"
```

> **Tip:** Run each command 2–3 times if the first enrollment isn't recognising you reliably (re-enrolling updates the embedding via Firestore `merge=True`).

---

## Firestore Collection Structure

```
firestore/
├── users/                    (FR-8: face identity registry)
│   └── usr_haseeb_abc123/
│       ├── user_id: "usr_haseeb_abc123"
│       ├── name: "Haseeb"
│       ├── role: "student"
│       ├── face_embedding: [0.12, -0.45, ...]  // 512 floats
│       └── preferences: { interests: ["AIML", "robotics"], language: "en" }
│
├── opportunities/            (FR-10: campus opportunities for recommendations)
│   └── opp_001/
│       ├── title: "AIML Research Internship"
│       ├── tags: ["AIML", "research", "machine_learning"]
│       └── ...
│
└── sessions/                 (optional — for Firestore-side session tracking)
```

---

## Testing Without InsightFace

If InsightFace isn't installed yet, you can test the Firebase client directly:

```python
# Run from project root
import sys; sys.path.insert(0, ".")
from backend.app.services.firebase_client import match_face, get_recommendations

# Simulate a known embedding (should NOT match — random vector)
fake_embedding = [0.0] * 512
fake_embedding[0] = 1.0  # unit vector

result = match_face(fake_embedding)
print(f"Match result: {result}")   # Should be None for random embedding

# Test recommendations for a seeded user
recs = get_recommendations("usr_haseeb_abc123")
print(f"Recommendations: {recs}")
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `FIREBASE_CREDENTIALS_PATH` | `firebase-credentials.json` | Path to service account key |
| `FACE_MATCH_THRESHOLD` | `0.85` | Cosine similarity cutoff (0–1) |
| `CAMERA_INDEX` | `0` | Webcam index for seed_faces.py |
