import httpx

url = "https://ai-kiosk-iota.vercel.app/api/navigation/87c8a7f8e7"
try:
    with httpx.Client() as client:
        resp = client.get(url, timeout=10.0)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
