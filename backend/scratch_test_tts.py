import asyncio
import logging
import sys

# Configure basic logging to see everything
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

from app.services.speech.tts_service import tts_service
from app.models.schemas import TTSRequest

async def test_tts():
    req = TTSRequest(
        session_id="test_tts_session",
        text="Hello, this is a test of the text to speech service.",
        language="en"
    )
    print("Starting TTS synthesis...")
    try:
        resp = await tts_service.synthesize(req)
        print("TTS Synthesis Succeeded!")
        print("Audio URL:", resp.audio_url)
        print("Duration:", resp.duration_seconds)
    except Exception as e:
        import traceback
        print("TTS Synthesis Failed!")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tts())
