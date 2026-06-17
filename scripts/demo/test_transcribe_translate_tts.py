"""
Interactive Multilingual Speech & Retrieval Pipeline Test Script
Owner: Antigravity

This script captures microphone input, performs VAD, runs Whisper ASR,
translates the query to English (if Kannada/Hindi), queries ChromaDB via CoordinatorAgent,
translates the retrieved answer back to the native language, and performs TTS output.
It runs in a loop so models are loaded only once.
"""

import asyncio
import base64
import os
import sys
import time

# Reconfigure stdout to use UTF-8 to prevent Windows console encoding errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root and backend are in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend")))

# Force real mode
os.environ["USE_MOCK_SERVICES"] = "False"

from backend.app.core.config import settings
settings.USE_MOCK_SERVICES = False

from backend.app.services.speech.audio_capture import audio_capture_service
from backend.app.services.speech.asr_service import asr_service
from backend.app.services.speech.tts_service import tts_service
from backend.app.models.schemas import ASRRequest, TTSRequest
from agents.coordinator.coordinator_agent import CoordinatorAgent
from deep_translator import GoogleTranslator

# Initialize global coordinator singleton
print("Warming up CoordinatorAgent and loading embedding model...")
coordinator = CoordinatorAgent()

async def main():
    print("=" * 80)
    print("      VidyaSahayak Multilingual Speech & Database Retrieval E2E Test")
    print("=" * 80)
    
    # Select language hint
    print("\nSelect Input Language Hint:")
    print("  [1] Auto-Detect")
    print("  [2] English ('en')")
    print("  [3] Hindi ('hi')")
    print("  [4] Kannada ('kn')")
    lang_choice = input("Enter choice [1-4] (default 1): ").strip()
    
    lang_hint = None
    if lang_choice == "2":
        lang_hint = "en"
    elif lang_choice == "3":
        lang_hint = "hi"
    elif lang_choice == "4":
        lang_hint = "kn"

    print("\nSelect Whisper Model Size:")
    print("  [1] base   (Fast, ~140MB)")
    print("  [2] medium (Recommended for Kannada/Hindi accuracy, ~1.5GB)")
    model_choice = input("Enter choice [1-2] (default 1): ").strip()
    model_size = "base"
    if model_choice == "2":
        model_size = "medium"

    # Override lazy-load method in ASR service to use chosen model size
    def custom_get_model():
        if asr_service.model is None:
            print(f"Loading faster-whisper model '{model_size}' on CPU...")
            from faster_whisper import WhisperModel
            asr_service.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print(f"faster-whisper model '{model_size}' loaded.")
        return asr_service.model
    asr_service._get_model = custom_get_model

    # Warm up Whisper model before entering loop
    print("Warming up Whisper model...")
    asr_service._get_model()
    print("Whisper model loaded.")

    # Ensure static directory exists
    os.makedirs(os.path.join("backend", "static", "audio"), exist_ok=True)
    test_wav_path = os.path.join("backend", "static", "audio", "e2e_interactive_test.wav")

    while True:
        print("\n" + "=" * 80)
        print("OPTIONS:")
        print("  * Press [Enter] to record query using microphone")
        print("  * Or type a text query directly")
        print("  * Or type 'quit' / 'exit' to exit")
        print("-" * 80)
        user_input = input("Your Input: ").strip()
        
        if user_input.lower() in ["quit", "exit"]:
            print("\nGoodbye!")
            break

        is_voice = (user_input == "")
        transcript = ""
        detected_lang = "en"

        if is_voice:
            print("\nMicrophone active. Speak now (VAD will stop recording after 1.5s of silence)...")
            # 1. Record Audio
            success = await audio_capture_service.record_until_silence(
                output_path=test_wav_path,
                silence_threshold=0.015,
                max_duration=15.0
            )

            if not success:
                print("\n[Error] Did not capture audio. Check if a microphone is connected and active.")
                continue

            print("\n>>> Audio captured successfully. Processing through Whisper ASR...")

            # 2. Base64 encode WAV bytes
            with open(test_wav_path, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            # 3. Transcribe Audio
            print("\n--- STEP 1: ASR Transcription ---")
            start = time.time()
            asr_req = ASRRequest(
                session_id="test_interactive_session",
                audio_base64=audio_base64,
                language_hint=lang_hint,
                turn_id=1
            )
            asr_resp = await asr_service.transcribe(asr_req)
            asr_latency = (time.time() - start) * 1000
            transcript = asr_resp.transcript
            detected_lang = asr_resp.detected_language.lower().split("-")[0]
            print(f"  ASR Transcript     : \"{transcript}\"")
            print(f"  Detected Language  : {asr_resp.detected_language.upper()} (prob: {asr_resp.confidence:.2f})")
            print(f"  ASR Latency        : {asr_latency:.2f} ms")

            # Cleanup recorded audio file
            if os.path.exists(test_wav_path):
                try:
                    os.remove(test_wav_path)
                except Exception:
                    pass

            if not transcript.strip():
                print("[Error] Empty transcript returned. Try speaking louder or closer.")
                continue
        else:
            # Direct text query
            transcript = user_input
            print("\n--- STEP 1: Text Input & Language Detection ---")
            # Auto-detect language using translator
            try:
                translator = GoogleTranslator(source="auto", target="en")
                translator.translate(transcript)
                detected_lang = translator._source.lower().split("-")[0]
            except Exception:
                detected_lang = lang_hint or "en"
            print(f"  Query Text         : \"{transcript}\"")
            print(f"  Detected Language  : {detected_lang.upper()}")

        # 4. Translate Query to English
        print("\n--- STEP 2: Query Translation ---")
        start = time.time()
        if detected_lang in ["kn", "hi"]:
            query_en = GoogleTranslator(source=detected_lang, target="en").translate(transcript)
            trans_query_latency = (time.time() - start) * 1000
            print(f"  Translated Query (en) : \"{query_en}\"")
            print(f"  Translation Latency   : {trans_query_latency:.2f} ms")
        else:
            query_en = transcript
            print("  Query is in English. Skipping translation.")

        # 5. Route and Retrieve from ChromaDB
        print("\n--- STEP 3: Database Routing & Retrieval ---")
        start = time.time()
        selected_domain, confidence, reason, all_matches = coordinator.route(query_en)
        print(f"  Matched Keywords   : {', '.join(all_matches) if all_matches else 'None'}")
        print(f"  Routed Agent       : {selected_domain.title() if selected_domain else 'None'} (confidence: {confidence:.2f})")
        print(f"  Routing Reason     : {reason}")
        
        if selected_domain and confidence > 0.0:
            agent = coordinator.agents[selected_domain]
            docs = agent.retrieve(query_en)
            if docs:
                answer_en = docs[0]["answer"]
                doc_id = docs[0]["id"]
                print(f"  Retrieved Doc ID   : {doc_id}")
                print(f"  Raw English Answer : \"{answer_en}\"")
            else:
                answer_en = f"I'm sorry, I couldn't find any information regarding that query in the {selected_domain} section."
                print("  [Warning] No docs matched in ChromaDB.")
        else:
            # Fallback message
            answer_en = (
                "I'm sorry, I couldn't identify the right department for your query.\n"
                "Please try asking about one of the following topics:\n"
                "- Admissions (requirements, application, fees, scholarships)\n"
                "- Academics (attendance, exams, SGPA/CGPA, transcripts)\n"
                "- Placements (internships, company eligibility, recruitment process)\n"
                "- Research (labs, publications, faculty projects, UROP)\n"
                "- Student Services (hostel, library, ID cards, certificate requests)\n"
                "- Navigation (campus directions, building/office locations)"
            )
            print("  [Warning] No keyword matches. Using default fallback directory.")
        
        db_latency = (time.time() - start) * 1000
        print(f"  Database Latency   : {db_latency:.2f} ms")

        # 6. Translate Answer Back
        print("\n--- STEP 4: Answer Translation ---")
        start = time.time()
        if detected_lang in ["kn", "hi"]:
            answer_native = GoogleTranslator(source="en", target=detected_lang).translate(answer_en)
            trans_resp_latency = (time.time() - start) * 1000
            print(f"  Translated Answer ({detected_lang}): \"{answer_native}\"")
            print(f"  Translation Latency      : {trans_resp_latency:.2f} ms")
        else:
            answer_native = answer_en
            print("  Output is in English. Skipping translation.")

        # 7. Generate TTS Audio
        print("\n--- STEP 5: TTS Synthesis ---")
        start = time.time()
        tts_req = TTSRequest(
            session_id="test_interactive_session",
            text=answer_native,
            language=detected_lang
        )
        tts_resp = await tts_service.synthesize(tts_req)
        tts_latency = (time.time() - start) * 1000
        print(f"  Audio Output Path  : {tts_resp.audio_url}")
        print(f"  Audio Duration     : {tts_resp.duration_seconds:.2f} s")
        print(f"  TTS Latency        : {tts_latency:.2f} ms")

        # 8. Playback Audio in Console
        print("\n--- STEP 6: Voice Playback ---")
        try:
            import pyttsx3
            print(f"Playing final voice feedback in {detected_lang}...")
            engine = pyttsx3.init()
            # Set target voice based on language
            if detected_lang != "en":
                voices = engine.getProperty("voices")
                for voice in voices:
                    if detected_lang in voice.languages or detected_lang in voice.name.lower():
                        engine.setProperty("voice", voice.id)
                        break
            engine.say(answer_native)
            engine.runAndWait()
        except Exception as e:
            print(f"Playback failed: {e}")

        print("\n" + "=" * 80)
        print("                       TURN PROCESSING COMPLETE")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
