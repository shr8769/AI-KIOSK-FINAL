import json
import re
import time
from typing import Any, Dict, Optional

from app.core.dependencies import (
    RIAR_ENABLED,
    get_coordinator_agent,
    translate_from_english,
    translate_to_english,
)
from app.core.logging import logger
from app.core.session_store import (
    add_agent_turn,
    add_user_turn,
    get_session,
)
from app.models.schemas import RIARRequest, TTSRequest, TurnModel
from app.services.riar_service import riar_service
from app.services.speech.tts_service import tts_service


async def run_query_pipeline(
    session_id: str, text: str, language_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core pipeline to process a text query.
    1. Detect language (English, Kannada, or Devanagari/Hindi).
    2. Translate to English if native language.
    3. Persist the turn history.
    4. Call RIAR Pipeline for domain mapping and ambiguity classification (if enabled).
    5. Query CoordinatorAgent.
    6. Translate the response back to user's native language.
    7. Synthesize TTS response.
    8. Store the query in PostgreSQL.
    """
    start_time = time.perf_counter()
    refined_query = None
    response_text = None
    domain = None
    ambiguity_type = "CLEAR"

    # Check if this is a language selection command
    from app.websockets.session_ws import _is_language_command

    lang_cmd = _is_language_command(text)
    if lang_cmd:
        confirmation_texts = {
            "en": "You selected English. How can I help you today?",
            "kn": "ಕನ್ನಡ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
            "hi": "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकता हूँ?",
        }
        text_response = confirmation_texts[lang_cmd]
        try:
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=text_response, language=lang_cmd)
            )
            audio_url = tts_resp.audio_url
        except Exception:
            audio_url = None

        return {
            "type": "answer",
            "text": text_response,
            "audio_url": audio_url,
            "sources": [],
            "navigation": None,
            "language": lang_cmd,
        }

    # 1. Detect language using character ranges first, then fallback to language_hint or en
    if any("\u0c80" <= c <= "\u0cff" for c in text):
        detected_lang = "kn"
    elif any("\u0900" <= c <= "\u097f" for c in text):
        detected_lang = "hi"
    else:
        detected_lang = language_hint or "en"

    clean_transcript = text

    # Translate to English if native language
    if detected_lang in ["kn", "hi"]:
        query_en = translate_to_english(clean_transcript, source_lang=detected_lang)
    else:
        query_en = clean_transcript
        detected_lang = "en"

    # Persist user turn
    await add_user_turn(session_id, clean_transcript)

    updated_session = await get_session(session_id)
    raw_history = updated_session.metadata.get("history", []) if updated_session else []
    history_turns = [
        TurnModel(turn_id=i + 1, role=t["role"], text=t["content"])
        for i, t in enumerate(raw_history)
    ]

    # 1.5 Quick Entity Resolution for Navigation
    import sys

    sys.path.append(r"c:\AI-KIOSK")
    try:
        from riar.retrievers.entity_resolver import EntityResolver

        if not hasattr(run_query_pipeline, "_entity_resolver"):
            run_query_pipeline._entity_resolver = EntityResolver()

        policy, top_loc = run_query_pipeline._entity_resolver.resolve(query_en)

        if policy == "ENTITY_DISAMBIGUATION" and top_loc:
            question_en = f"Did you mean {top_loc['name']}?"
            question_native = (
                translate_from_english(question_en, target_lang=detected_lang)
                if detected_lang in ["kn", "hi"]
                else question_en
            )
            await add_agent_turn(session_id, question_native)

            try:
                tts_resp = await tts_service.synthesize(
                    TTSRequest(session_id=session_id, text=question_native, language=detected_lang)
                )
                audio_url = tts_resp.audio_url
            except Exception:
                audio_url = None

            return {
                "type": "clarifying",
                "text": question_native,
                "audio_url": audio_url,
                "ambiguity_type": "ENTITY_DISAMBIGUATION",
                "sources": [],
                "navigation": None,
                "language": detected_lang,
            }

        elif policy == "DIRECT" and top_loc:
            try:
                from app.services.navigation_service import navigation_service

                nav_id = await navigation_service.create_session(top_loc)

                answer_en = f"The {top_loc.get('name')} is located in {top_loc.get('building')}, Floor {top_loc.get('floor')}. Please scan the QR code for detailed directions."
                answer_native = (
                    translate_from_english(answer_en, target_lang=detected_lang)
                    if detected_lang in ["kn", "hi"]
                    else answer_en
                )
                await add_agent_turn(session_id, answer_native)

                try:
                    tts_text = re.sub(r"[*_#]", "", answer_native)
                    tts_resp = await tts_service.synthesize(
                        TTSRequest(session_id=session_id, text=tts_text, language=detected_lang)
                    )
                    audio_url = tts_resp.audio_url
                except Exception:
                    audio_url = None

                return {
                    "type": "answer",
                    "text": answer_native,
                    "audio_url": audio_url,
                    "sources": [],
                    "navigation": {
                        "navigation_id": nav_id,
                        "destination_name": top_loc.get("name"),
                        "building": top_loc.get("building"),
                        "floor": top_loc.get("floor"),
                        "room": top_loc.get("room"),
                    },
                    "language": detected_lang,
                }
            except Exception as e:
                logger.error(f"Fast-path navigation failed: {e}")
    except Exception as e:
        logger.error(f"EntityResolver initialization or execution failed: {e}")

    # 2. RIAR classification
    ambiguous = False
    riar_resp = None
    if RIAR_ENABLED:
        try:
            riar_resp = await riar_service.classify(
                RIARRequest(
                    session_id=session_id,
                    turn_id=len(history_turns) + 1,
                    query=query_en,
                    language="en",
                    session_history=history_turns,
                )
            )
            ambiguous = getattr(
                riar_resp, "requires_clarification", getattr(riar_resp, "ambiguity_detected", False)
            )
        except Exception as e:
            logger.error(f"RIAR classification failed, falling back to clear search: {e}")

    if ambiguous:
        question_en = riar_resp.clarification_question or "Could you clarify your question?"
        question_native = translate_from_english(question_en, target_lang=detected_lang)
        await add_agent_turn(session_id, question_native)

        response_text = question_native
        ambiguity_type = riar_resp.ambiguity_type if riar_resp else "CLEAR"
        domain = None

        try:
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=question_native, language=detected_lang)
            )
            audio_url = tts_resp.audio_url
        except Exception as e:
            logger.error(f"TTS Synthesis failed for clarification: {e}")
            audio_url = None

        result = {
            "type": "clarifying",
            "text": question_native,
            "audio_url": audio_url,
            "ambiguity_type": ambiguity_type,
            "sources": [],
            "navigation": None,
            "language": detected_lang,
        }
    else:
        refined_query = (
            getattr(riar_resp, "refined_query", None) or query_en if riar_resp else query_en
        )

        target_domain = getattr(riar_resp, "selected_domain", None) if riar_resp else None
        if not target_domain or target_domain == "general":
            query_lower = refined_query.lower()
            if "admission" in query_lower:
                target_domain = "admissions"
            elif "academic" in query_lower or "course" in query_lower or "grade" in query_lower:
                target_domain = "academics"
            elif (
                "placement" in query_lower
                or "salary" in query_lower
                or "job" in query_lower
                or "company" in query_lower
                or "recruit" in query_lower
            ):
                target_domain = "placements"
            elif (
                "research" in query_lower
                or "paper" in query_lower
                or "publication" in query_lower
                or "project" in query_lower
            ):
                target_domain = "research"
            elif (
                "student" in query_lower
                or "hostel" in query_lower
                or "fee" in query_lower
                or "scholarship" in query_lower
            ):
                target_domain = "student_services"
            elif (
                "where" in query_lower
                or "locate" in query_lower
                or "direction" in query_lower
                or "floor" in query_lower
                or "room" in query_lower
                or "building" in query_lower
                or "map" in query_lower
            ):
                target_domain = "navigation"
            else:
                target_domain = "general"

        coordinator = get_coordinator_agent()
        import asyncio

        full_answer = await asyncio.to_thread(
            coordinator.answer, refined_query, target_domain=target_domain
        )

        nav_payload = None
        citations = []

        if target_domain == "navigation":
            try:
                metadata = json.loads(full_answer)
                if "error" not in metadata:
                    from app.services.navigation_service import navigation_service

                    nav_id = await navigation_service.create_session(metadata)

                    answer_en = f"The {metadata.get('destination_name')} is located in {metadata.get('building')}, Floor {metadata.get('floor')}. Please scan the QR code for detailed directions."
                    nav_payload = {
                        "navigation_id": nav_id,
                        "destination_name": metadata.get("destination_name"),
                        "building": metadata.get("building"),
                        "floor": metadata.get("floor"),
                        "room": metadata.get("room"),
                    }
                else:
                    answer_en = metadata["error"]
            except Exception as e:
                logger.error(f"Failed to parse navigation JSON: {e}")
                answer_en = "I'm sorry, I couldn't retrieve the location details."
        else:
            if "\n\n[Source: " in full_answer:
                parts = full_answer.split("\n\n[Source: ", 1)
                answer_en = parts[0]
                citations = [parts[1].rstrip("]")]
            else:
                answer_en = full_answer

        answer_native = (
            translate_from_english(answer_en, target_lang=detected_lang)
            if detected_lang in ("kn", "hi")
            else answer_en
        )
        await add_agent_turn(session_id, answer_native)

        response_text = answer_native
        ambiguity_type = getattr(riar_resp, "ambiguity_type", "CLEAR") if riar_resp else "CLEAR"
        domain = target_domain

        tts_text = re.sub(r"[*_#]", "", answer_native)
        try:
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=tts_text, language=detected_lang)
            )
            audio_url = tts_resp.audio_url
        except Exception as e:
            logger.error(f"TTS Synthesis failed: {e}")
            audio_url = None

        result = {
            "type": "answer",
            "text": answer_native,
            "audio_url": audio_url,
            "sources": citations,
            "navigation": nav_payload,
            "language": detected_lang,
        }

    # PostgreSQL Turn Logging
    try:
        from database.models.models import Session as PGSession
        from database.postgres.connection import AsyncSessionLocal
        from sqlalchemy.future import select

        from app.services.query_store import QueryStore

        user_id = None
        async with AsyncSessionLocal() as db_session:
            sess_res = await db_session.execute(
                select(PGSession).filter(PGSession.session_id == session_id)
            )
            db_sess = sess_res.scalars().first()
            if db_sess:
                user_id = db_sess.user_id

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        async with AsyncSessionLocal() as db_session:
            store = QueryStore(db_session)
            await store.store_query(
                session_id=session_id,
                user_id=user_id,
                query_text=clean_transcript,
                refined_query=refined_query,
                response_text=response_text,
                domain=domain,
                language=detected_lang,
                ambiguity_type=ambiguity_type,
                latency_ms=latency_ms,
            )
    except Exception as db_e:
        logger.error(f"Failed to log user query to PostgreSQL: {db_e}")

    return result
