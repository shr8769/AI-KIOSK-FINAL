import os
import httpx

url = "https://sweet-lark-71243.upstash.io/"
token = '"gQAAAAAAARZLAAIgcDFkZTFjN2IyZWM4Njk0NDc5YmQzOTBmYWYyM2I1OTRjMQ"'

headers = {"Authorization": f"Bearer {token}"}
payload = ["SET", "test_key", "test_value"]

try:
    with httpx.Client() as client:
        resp = client.post(url, json=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")
