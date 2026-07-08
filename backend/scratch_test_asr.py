import asyncio
import logging
import sys

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

from app.services.speech.asr_service import asr_service
from app.models.schemas import ASRRequest

async def test_asr():
    # 1-second silent WAV base64
    silent_wav_b64 = (
        "UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAAA"
    )
    
    req = ASRRequest(
        session_id="test_asr_session",
        audio_base64=silent_wav_b64,
        language_hint="en",
        turn_id=1
    )
    
    print("Starting ASR transcription...")
    try:
        resp = await asr_service.transcribe(req)
        print("ASR Succeeded!")
        print("Transcript:", repr(resp.transcript))
        print("Detected Language:", resp.detected_language)
    except Exception as e:
        import traceback
        print("ASR Failed!")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_asr())
