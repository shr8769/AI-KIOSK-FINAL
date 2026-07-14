import os
from dotenv import load_dotenv
import httpx
import json

load_dotenv("backend/.env")
url = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/") + "/"
token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
headers = {"Authorization": f"Bearer {token}"}
payload = ["KEYS", "nav:*"]

try:
    with httpx.Client() as client:
        resp = client.post(url, json=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
