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
from app.services.speech.tts_service import tts_service
from app.services.fast_router import get_strict_fast_path_domain


def local_spelling_corrector(query: str) -> str:
    import difflib
    STANDARD_TERMS = [
        "microsoft", "admissions", "placement", "placements", "scholarship", "scholarships",
        "internship", "internships", "academic", "academics", "hostel", "hostels",
        "canteen", "library", "office", "entrance", "fees", "admission"
    ]
    words = query.split()
    corrected_words = []
    for w in words:
        clean_w = re.sub(r"[^\w]", "", w.lower())
        if not clean_w:
            corrected_words.append(w)
            continue
        if len(clean_w) >= 4:
            matches = difflib.get_close_matches(clean_w, STANDARD_TERMS, n=1, cutoff=0.75)
            if matches:
                punc = re.search(r"[^\w]+$", w)
                suffix = punc.group(0) if punc else ""
                corrected_words.append(matches[0] + suffix)
                continue
        corrected_words.append(w)
    return " ".join(corrected_words)


async def correct_and_normalize_query(query: str) -> str:
    """
    Spelling correction and semantic query normalization.
    Fixes spelling errors and rephrases input into clear English matching target vocabulary.
    """
    # 1. Run local spelling correction fast-path
    try:
        query = local_spelling_corrector(query)
    except Exception as e:
        logger.error(f"Local spelling correction failed: {e}")

    # Bypass LLM query normalization entirely to save latency (saves ~500ms-1s per turn)
    return query


async def make_conversational(text: str, lang: str) -> str:
    """
    Post-process a formally-translated Kannada or Hindi response into a
    natural, code-mixed (Kanglish / Hinglish) conversational style.

    The key insight: pure machine-translated Kannada/Hindi sounds robotic.
    We ask the LLM to rephrase it so it flows like how educated urban Indians
    actually speak — mixing English nouns/brands/numbers with Kannada or Hindi
    grammar, contractions, and friendly tone.
    """
    if lang not in ("kn", "hi"):
        return text

    lang_name = {"kn": "Kannada", "hi": "Hindi"}[lang]
    mix_example = {
        "kn": (
            "Example:\n"
            "  Formal: 'ವಿದ್ಯಾರ್ಥಿಗಳ ನೇಮಕಾತಿ ಮಾಹಿತಿಗಾಗಿ placement cell ಗೆ ಸಂಪರ್ಕಿಸಿ.'\n"
            "  Conversational: 'Placement ಬಗ್ಗೆ ತಿಳಿಯಬೇಕಾದ್ರೆ, placement cell ಅನ್ನ directly contact ಮಾಡ್ಬಹುದು!'\n"
        ),
        "hi": (
            "Example:\n"
            "  Formal: 'छात्रों के लिए placement सेल से संपर्क करें.'\n"
            "  Conversational: 'Placement के बारे में जानना है, toh placement cell ko directly contact kar sakte ho!'\n"
        ),
    }[lang]

    prompt = (
        f"You are a friendly university AI kiosk assistant. "
        f"Rewrite the following {lang_name} text to sound natural and conversational, "
        f"like how educated urban Indians actually speak — mixing {lang_name} grammar with "
        f"common English words (technical terms, brand names, numbers, and short phrases can stay in English). "
        f"CRITICAL: You MUST write the final output entirely in the Roman alphabet (English/Latin letters/Hinglish). Do NOT use Devanagari or Kannada scripts. "
        f"Keep all factual information exactly the same. Do NOT translate everything to English. "
        f"Keep it warm, friendly, and short. Return ONLY the rewritten Romanized text, no explanation.\n"
        f"{mix_example}\n"
        f"Text to rewrite:\n{text}\n"
        f"Conversational Romanized {lang_name} version:"
    )

    try:
        import asyncio

        from app.core.dependencies import get_riar_pipeline
        pipeline = get_riar_pipeline()
        llm = pipeline.llm_client
        response = await asyncio.to_thread(llm.invoke, prompt)
        result = response.content.strip().strip('"').strip("'")
        if result and len(result) >= 5:
            logger.info(f"make_conversational ({lang}): '{text[:50]}' -> '{result[:50]}'")
            return result
    except Exception as e:
        logger.warning(f"make_conversational failed ({lang}): {e}")
    return text


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

    # 1. Detect language and preprocess Romanized queries
    from app.services.speech.translation_service import preprocess_and_detect_language
    clean_transcript, detected_lang = preprocess_and_detect_language(text, language_hint)

    # Translate to English if native language
    if detected_lang in ["kn", "hi"]:
        import asyncio
        query_en = await asyncio.to_thread(translate_to_english, clean_transcript, source_lang=detected_lang)
    else:
        query_en = clean_transcript

    # Check for outstanding clarification response
    updated_session = await get_session(session_id)
    outstanding = None
    if updated_session and updated_session.metadata:
        outstanding = updated_session.metadata.get("outstanding_clarification")

    if not outstanding:
        # Check for contextual pronouns and implicitly resolve them using history
        query_en_lower = query_en.lower()
        if re.search(r'\b(it|its|they|them|their|he|his|she|her|there)\b', query_en_lower):
            if updated_session:
                history = updated_session.metadata.get("history", [])
                if len(history) >= 2:
                    # Find the last answer given by the agent
                    last_agent_turn = None
                    for turn in reversed(history):
                        if turn.get("role") == "agent":
                            last_agent_turn = turn
                            break
                    
                    if last_agent_turn:
                        try:
                            from app.core.dependencies import get_riar_pipeline
                            import asyncio
                            pipeline = get_riar_pipeline()
                            prompt = f"Given the previous answer: '{last_agent_turn.get('content')}', rewrite this query to be clear and self-contained by replacing pronouns with the subject: '{query_en}'\nOutput ONLY the rewritten query. If it cannot be resolved, output the original query."
                            response = await asyncio.to_thread(pipeline.llm_client.invoke, prompt)
                            rewritten = response.content.strip().strip('"').strip("'")
                            if rewritten and rewritten.lower() != query_en_lower:
                                logger.info(f"Implicit Context Resolution: '{query_en}' -> '{rewritten}'")
                                query_en = rewritten
                        except Exception as e:
                            logger.error(f"Contextual rewrite failed: {e}")

    was_refined = False
    if outstanding:
        was_refined = True
        from app.core.dependencies import get_riar_pipeline
        pipeline = get_riar_pipeline()

        orig_q = outstanding.get("original_query")
        clar_q = outstanding.get("clarification_question")
        amb_t = outstanding.get("ambiguity_type", "CLEAR")

        import asyncio
        refined_res = await asyncio.to_thread(
            pipeline.refine,
            original_query=orig_q,
            clarification_response=query_en,
            ambiguity_type=amb_t,
            clarification_question=clar_q
        )
        logger.info(f"RIAR Merged query: '{orig_q}' + response '{query_en}' -> '{refined_res.refined_query}'")
        query_en = refined_res.refined_query

        from app.core.session_store import update_session_metadata
        await update_session_metadata(session_id, {"outstanding_clarification": None})

        # Reload the updated session to get the latest DB metadata
        updated_session = await get_session(session_id)

    # Correct and normalize spelling/phrasing variations
    query_en = await correct_and_normalize_query(query_en)

    # Persist user turn
    await add_user_turn(session_id, clean_transcript)

    raw_history = updated_session.metadata.get("history", []) if updated_session else []
    history_turns = [
        TurnModel(turn_id=i + 1, role=t["role"], text=t["content"])
        for i, t in enumerate(raw_history)
    ]

    # 2. Fast-Path Router (Bypass LLM for common demo intents)
    fast_domain = get_strict_fast_path_domain(query_en)
    
    # 1.5 Quick Entity Resolution for Navigation
    if not fast_domain:
        import sys
        sys.path.append(r"c:\AI-KIOSK")
        try:
            from riar.retrievers.entity_resolver import EntityResolver
    
            if not hasattr(run_query_pipeline, "_entity_resolver"):
                run_query_pipeline._entity_resolver = EntityResolver()
    
            policy, top_loc = run_query_pipeline._entity_resolver.resolve(query_en)
    
            if policy == "ENTITY_DISAMBIGUATION" and top_loc:
                question_en = f"Did you mean {top_loc['name']}?"
                import asyncio
                question_native = (
                    await asyncio.to_thread(translate_from_english, question_en, target_lang=detected_lang)
                    if detected_lang in ["kn", "hi"]
                    else question_en
                )
                if detected_lang in ("kn", "hi"):
                    question_native = await make_conversational(question_native, detected_lang)
                await add_agent_turn(session_id, question_native)
    
                try:
                    tts_resp = await tts_service.synthesize(
                        TTSRequest(session_id=session_id, text=question_native, language=detected_lang)
                    )
                    audio_url = tts_resp.audio_url
                except Exception:
                    audio_url = None
    
                from app.core.session_store import update_session_metadata
                await update_session_metadata(
                    session_id,
                    {
                        "outstanding_clarification": {
                            "original_query": query_en,
                            "clarification_question": question_en,
                            "ambiguity_type": "ENTITY_DISAMBIGUATION",
                        }
                    }
                )
    
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
                    nav_url = navigation_service.build_url(nav_id)
    
                    answer_en = f"The {top_loc.get('name')} is located in {top_loc.get('building')}, Floor {top_loc.get('floor')}. Please scan the QR code for detailed directions."
                    import asyncio
                    answer_native = (
                        await asyncio.to_thread(translate_from_english, answer_en, target_lang=detected_lang)
                        if detected_lang in ["kn", "hi"]
                        else answer_en
                    )
                    if detected_lang in ("kn", "hi"):
                        answer_native = await make_conversational(answer_native, detected_lang)
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
                            "url": nav_url,
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
    ambiguous = False
    riar_resp = None
    
    if fast_domain:
        logger.info(f"Fast-path matched for text query '{query_en}' -> {fast_domain}")
        target_domain = fast_domain
        refined_query = query_en
    else:
        # 2a. RIAR classification
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
                ambiguous = getattr(riar_resp, "requires_clarification", getattr(riar_resp, "ambiguity_detected", False))
            except Exception as e:
                import httpx
                if isinstance(e, httpx.ReadTimeout):
                    logger.error("RIAR classification timed out")
                else:
                    logger.error(f"RIAR classification failed, falling back to clear search: {e}")
                ambiguous = False
                riar_resp = None

    if ambiguous:
        question_en = riar_resp.clarification_question or "Could you clarify your question?"
        import asyncio
        question_native = await asyncio.to_thread(translate_from_english, question_en, target_lang=detected_lang)
        if detected_lang in ("kn", "hi"):
            question_native = await make_conversational(question_native, detected_lang)
        await add_agent_turn(session_id, question_native)

        response_text = question_native
        ambiguity_type = riar_resp.ambiguity_type if riar_resp else "CLEAR"
        domain = None

        from app.core.session_store import update_session_metadata
        await update_session_metadata(
            session_id,
            {
                "outstanding_clarification": {
                    "original_query": query_en,
                    "clarification_question": question_en,
                    "ambiguity_type": ambiguity_type,
                }
            }
        )

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
        # 3. FAQ Retrieval
        if not fast_domain:
            refined_query = getattr(riar_resp, "refined_query", None) or query_en if riar_resp else query_en
            target_domain = getattr(riar_resp, "selected_domain", None) if riar_resp else None
            
            # Fallback heuristics for RIAR mapping
            if not target_domain or target_domain == "general":
                query_lower = refined_query.lower()
                if "admission" in query_lower:
                    target_domain = "admissions"
                elif "academic" in query_lower or "course" in query_lower or "grade" in query_lower:
                    target_domain = "academics"
                elif "placement" in query_lower or "salary" in query_lower or "job" in query_lower or "company" in query_lower or "recruit" in query_lower:
                    target_domain = "placements"
                elif "research" in query_lower or "paper" in query_lower or "publication" in query_lower or "project" in query_lower:
                    target_domain = "research"
                elif "student" in query_lower or "hostel" in query_lower or "fee" in query_lower or "scholarship" in query_lower:
                    target_domain = "student_services"
                elif "where" in query_lower or "locate" in query_lower or "direction" in query_lower or "floor" in query_lower or "room" in query_lower or "building" in query_lower or "map" in query_lower:
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
        is_fallback = False

        if target_domain == "navigation":
            try:
                metadata = json.loads(full_answer)
                if "error" not in metadata:
                    from app.services.navigation_service import navigation_service

                    nav_id = await navigation_service.create_session(metadata)
                    nav_url = navigation_service.build_url(nav_id)

                    from app.core.config import get_local_ip
                    answer_en = f"The {metadata.get('destination_name')} is located in {metadata.get('building')}, Floor {metadata.get('floor')}. Please scan the QR code for detailed directions."
                    nav_payload = {
                        "navigation_id": nav_id,
                        "url": nav_url,
                        "destination_name": metadata.get("destination_name"),
                        "building": metadata.get("building"),
                        "floor": metadata.get("floor"),
                        "room": metadata.get("room"),
                        "kiosk_ip": get_local_ip()
                    }
                else:
                    answer_en = metadata["error"]
                    is_fallback = True
            except Exception as e:
                logger.error(f"Failed to parse navigation JSON: {e}")
                answer_en = "I'm sorry, I couldn't retrieve the location details."
                is_fallback = True
        else:
            if "\n\n[Source: " in full_answer:
                parts = full_answer.split("\n\n[Source: ", 1)
                answer_en = parts[0]
                citations = [parts[1].rstrip("]")]
            else:
                answer_en = full_answer

            is_fallback = "[Source: None]" in full_answer or "I encountered an error retrieving that information." in full_answer or "could not find information regarding this" in full_answer.lower() or "location not found" in full_answer.lower()

        if is_fallback:
            if not was_refined:
                # Evidence is not clear/sufficient, question back the user for clarification first
                try:
                    from app.core.dependencies import get_riar_pipeline
                    pipeline = get_riar_pipeline()
                    llm = pipeline.llm_client
                except Exception:
                    llm = None

                question_prompt = f"""You are the Clarification Engine for VidyaSahayak, the PES University Kiosk.
The user asked a query that couldn't be answered clearly with the current knowledge base: "{query_en}"
Since the retrieved evidence is not clear or sufficient, generate a polite clarification question asking the user to provide more specific details, rephrase, or specify their requirements so we can search the knowledge base again.
Strictly return ONLY the clarification question. Do not include any explanations, markdown, or quotes.
Clarification Question:"""

                question_en = "I'm sorry, I couldn't find clear information on that. Could you please provide more details or specify what you are looking for?"
                if llm:
                    try:
                        import asyncio
                        response = await asyncio.to_thread(llm.invoke, question_prompt)
                        question_en = response.content.strip().strip('"').strip("'").strip()
                    except Exception as e:
                        logger.error(f"Failed to generate clarification question using LLM: {e}")

                import asyncio
                question_native = await asyncio.to_thread(translate_from_english, question_en, target_lang=detected_lang)
                if detected_lang in ("kn", "hi"):
                    question_native = await make_conversational(question_native, detected_lang)
                await add_agent_turn(session_id, question_native)

                from app.core.session_store import update_session_metadata
                await update_session_metadata(
                    session_id,
                    {
                        "outstanding_clarification": {
                            "original_query": query_en,
                            "clarification_question": question_en,
                            "ambiguity_type": "CONTEXTUAL",
                        }
                    }
                )

                try:
                    tts_resp = await tts_service.synthesize(
                        TTSRequest(session_id=session_id, text=question_native, language=detected_lang)
                    )
                    audio_url = tts_resp.audio_url
                except Exception as e:
                    logger.error(f"TTS Synthesis failed for clarification: {e}")
                    audio_url = None

                return {
                    "type": "clarifying",
                    "text": question_native,
                    "audio_url": audio_url,
                    "ambiguity_type": "CONTEXTUAL",
                    "sources": [],
                    "navigation": None,
                    "language": detected_lang,
                }

            # Escalation flow!
            # 1. Fetch user details from database using updated_session.user_id
            user_name = "Guest User"
            contact_number = "Not Provided"

            if updated_session and updated_session.metadata:
                u_id = updated_session.metadata.get("user_id")
                u_name = updated_session.metadata.get("user_name")
                if u_id:
                    contact_number = u_id
                if u_name:
                    user_name = u_name

                # Query Postgres User to get more accurate name or contact info if they registered
                if u_id and u_id != "usr_guest":
                    from database.models.models import User as PGUser
                    from database.postgres.connection import AsyncSessionLocal
                    from sqlalchemy.future import select

                    try:
                        async with AsyncSessionLocal() as db_session:
                            q = select(PGUser).where(PGUser.user_id == u_id)
                            res = await db_session.execute(q)
                            pg_user = res.scalar_one_or_none()
                            if pg_user:
                                user_name = pg_user.name
                                contact_number = pg_user.preferences.get("phone_number") or pg_user.user_id
                    except Exception as e:
                        logger.error(f"Failed to fetch user for escalation: {e}")

            # Map domain to corresponding office details
            OFFICE_DETAILS = {
                "admissions": "Admissions Office: Main Building, Ground Floor. Contact: +91 80 2672 1983, Email: admissions@pes.edu",
                "academics": "Academic Block Office: B-Block, 1st Floor. Contact: +91 80 2672 2011, Email: academics@pes.edu",
                "placements": "Placement & Career Guidance Cell: C-Block, 3rd Floor. Contact: +91 80 2672 2022, Email: placements@pes.edu",
                "research": "Research Center: R-Block, 2nd Floor. Contact: research@pes.edu",
                "student_services": "Student Affairs Office: Main Building, 1st Floor. Contact: student_services@pes.edu",
                "navigation": "Campus Information Desk: Entrance Gate. Contact: info@pes.edu",
                "general": "Main Administrative Office: Main Building, Ground Floor. Contact: admin@pes.edu"
            }

            office_info = OFFICE_DETAILS.get(target_domain or "general", OFFICE_DETAILS["general"])
            answer_en = (
                f"I could not find information regarding this in the university knowledge base. "
                f"Please contact the relevant office:\n{office_info}.\n"
                f"We have registered this query with your contact details and escalated it to them."
            )
            citations = []

            # Save the escalation ticket to postgres
            try:
                from database.models.models import OfficeEscalation
                from database.postgres.connection import AsyncSessionLocal

                async with AsyncSessionLocal() as db_session:
                    escalation = OfficeEscalation(
                        customer_name=user_name,
                        contact_number=contact_number,
                        domain=target_domain or "general",
                        office_details=office_info,
                        issue_encountering=refined_query or query_en
                    )
                    db_session.add(escalation)
                    await db_session.commit()
                    logger.info(f"Successfully recorded office escalation ticket to database for '{user_name}' / '{contact_number}'.")
            except Exception as e:
                logger.error(f"Failed to record office escalation ticket: {e}")

        import asyncio
        answer_native = (
            await asyncio.to_thread(translate_from_english, answer_en, target_lang=detected_lang)
            if detected_lang in ("kn", "hi")
            else answer_en
        )
        if detected_lang in ("kn", "hi"):
            answer_native = await make_conversational(answer_native, detected_lang)
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
        
        async def log_to_db():
            try:
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
            except Exception as e:
                logger.error(f"Background DB logging failed: {e}")
                
        import asyncio
        asyncio.create_task(log_to_db())

    except Exception as db_e:
        logger.error(f"Failed to setup background DB logging: {db_e}")

    return result
