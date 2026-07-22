import asyncio
import websockets
import json
import time

WS_URL = "ws://localhost:8000/api/v1/chat/stress-test-session"

TEST_QUERIES = [
    "What are the eligibility requirements for B.Tech?",
    "How many campuses does PES University have?",
    "Which top tier-1 companies visit the campus for placements?",
    "Are there any pre-placement training programs?",
    "What is the minimum attendance required to write exams?",
    "How do I join a club on campus?",
    "Can you give me directions to the library?",
    "What happens if I get a backlog?",
    "Are there any scholarships for international students?",
    "Tell me a joke." # Out of scope test
]

async def send_query(query_text, idx):
    start_time = time.time()
    try:
        async with websockets.connect(WS_URL) as ws:
            payload = {
                "type": "text_query",
                "payload": {
                    "text": query_text,
                    "language": "en"
                }
            }
            await ws.send(json.dumps(payload))
            response = await ws.recv()
            latency = time.time() - start_time
            print(f"[Query {idx}] Latency: {latency:.2f}s | Success")
            return latency
    except Exception as e:
        print(f"[Query {idx}] Failed: {e}")
        return -1

async def main():
    print(f"Starting stress test with 3 concurrent connections...")
    tasks = []
    for i, query in enumerate(TEST_QUERIES[:3]):
        tasks.append(asyncio.create_task(send_query(query, i)))
    
    results = await asyncio.gather(*tasks)
    
    successful = [r for r in results if r > 0]
    if successful:
        print(f"\n--- Stress Test Results ---")
        print(f"Total Requests: {len(TEST_QUERIES)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(TEST_QUERIES) - len(successful)}")
        print(f"Average Latency: {sum(successful) / len(successful):.2f}s")
        print(f"Max Latency: {max(successful):.2f}s")
        print(f"Min Latency: {min(successful):.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
