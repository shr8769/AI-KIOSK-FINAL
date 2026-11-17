import re
import time
from typing import Any, Dict, Optional

from app.core.dependencies import (
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
from app.models.schemas import TTSRequest
from app.services.fast_router import get_strict_fast_path_domain
from app.services.speech.tts_service import tts_service


def _clean_agent_answer(raw: str) -> str:
    """Strip internal formatting artifacts from agent responses."""
    text = raw
    # Strip "Answer:\n" prefix
    if text.startswith("Answer:\n"):
        text = text[len("Answer:\n"):].strip()
    elif text.startswith("Answer:"):
        text = text[len("Answer:"):].strip()
    # Strip "\n\nSources:\n    ..." suffix
    if "\n\nSources:\n" in text:
        text = text.split("\n\nSources:\n")[0].strip()
    # Strip "[Source: ...]" suffix
    if "\n\n[Source: " in text:
        text = text.split("\n\n[Source: ")[0].strip()
    return text


def _is_fallback_answer(text: str) -> bool:
    """Check if the answer is a fallback / not-found response."""
    lower = text.lower()
    return any(marker in lower for marker in [
        "could not find information",
        "i encountered an error",
        "location not found",
        "[source: none]",
    ])


def ensure_clickable_links(text: str) -> str:
    """
    Ensures that all URLs, emails, and phone numbers in the text are properly
    formatted as clickable Markdown links across all languages (en, kn, hi).
    Fixes mangled translated markdown links like 'ಈ ಲಿಂಕ್ (https://...'
    """
    if not text:
        return text

    # Step 1: Repair unclosed or mangled translated markdown links
    # e.g. "ಈ ಲಿಂಕ್ (https://pes.edu/admissions/" -> "[ಈ ಲಿಂಕ್](https://pes.edu/admissions/)"
    text = re.sub(
        r'(\b[^\n\r()[\]]+?)\s*\(\s*(https?://[^\s)]+)\s*\)?',
        r'[\1](\2)',
        text
    )

    # Step 2: Extract existing valid markdown links to placeholders
    links = []
    def save_link(m):
        links.append(m.group(0))
        return f"__MD_LINK_{len(links)-1}__"

    text = re.sub(r'\[[^\]]+\]\([^\)]+\)', save_link, text)

    # Step 3: Autolink bare URLs
    text = re.sub(r'(https?://[^\s<>()]+)', r'[\1](\1)', text)

    # Step 4: Autolink email addresses
    text = re.sub(r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b', r'[\1](mailto:\1)', text)

    # Step 5: Restore placeholders
    for idx, l in enumerate(links):
        text = text.replace(f"__MD_LINK_{idx}__", l)

    return text



def local_spelling_corrector(query: str) -> str:
    import difflib

    from app.core.dependencies import get_coordinator_agent

    try:
        coordinator = get_coordinator_agent()
        standard_terms_set = set()
        for keywords in coordinator.routing_rules.values():
            for kw in keywords:
                for word in kw.split():
                    if len(word) >= 4:
                        standard_terms_set.add(word.lower())
        STANDARD_TERMS = list(standard_terms_set)
    except Exception:
        STANDARD_TERMS = [
            "microsoft", "admissions", "placement", "placements", "scholarship", "scholarships",
            "internship", "internships", "academic", "academics", "hostel", "hostels",
            "canteen", "library", "office", "entrance", "fees", "admission", "attendance", "engineering"
        ]
    words = query.split()
    corrected_words = []
    for w in words:
        clean_w = re.sub(r"[^\w]", "", w.lower())
        if not clean_w:
            corrected_words.append(w)
            continue
        if len(clean_w) >= 4:
            matches = difflib.get_close_matches(clean_w, STANDARD_TERMS, n=1, cutoff=0.85)
            if matches:
                punc = re.search(r"[^\w]+$", w)
                suffix = punc.group(0) if punc else ""
                corrected_words.append(matches[0] + suffix)
                continue
        corrected_words.append(w)
    return " ".join(corrected_words)


async def correct_and_normalize_query(query: str, detected_lang: str) -> str:
    """
    Spelling correction and semantic query normalization.
    Fixes spelling errors and rephrases input into clear English matching target vocabulary.
    """
    # Hardcoded phonetic fallbacks for ASR errors
    query_lower = query.lower()
    query_lower = query_lower.replace("passage", "pessat")
    query_lower = query_lower.replace("pesat", "pessat")
    query_lower = query_lower.replace("p stat", "pessat")
    query_lower = query_lower.replace("k set", "kcet")
    query_lower = re.sub(r'\bkota\b', 'quota', query_lower)
    query_lower = query_lower.replace("et quota", "KCET quota")
    query_lower = query_lower.replace("e t quota", "KCET quota")
    query_lower = query_lower.replace("cet quota", "KCET quota")
    query_lower = query_lower.replace("et admission", "KCET admission")
    query_lower = query_lower.replace("cet admission", "KCET admission")
    query_lower = query_lower.replace("v tech", "B.Tech")
    query_lower = query_lower.replace("be tech", "B.Tech")
    query_lower = query_lower.replace("btech", "B.Tech")
    query_lower = query_lower.replace("b tech", "B.Tech")
    query_lower = query_lower.replace("mrd", "Prof. MRD Scholarship")
    
    # Alumni phonetic fallbacks
    query_lower = query_lower.replace("aluminium", "alumni")
    query_lower = query_lower.replace("aluminy", "alumni")
    query_lower = query_lower.replace("best alumni", "pes alumni")
    query_lower = query_lower.replace("base alumni", "pes alumni")
    
    # University ASR phonetic fallbacks (e.g. 'at TS' -> 'at PES')
    query_lower = re.sub(r'\b(at\s+ts|in\s+ts|at\s+ps|in\s+ps|at\s+base|in\s+base|at\s+best)\b', 'at PES', query_lower)
    query_lower = re.sub(r'\bts\s+(university|college|campus)\b', 'PES University', query_lower)
    
    # Placement and time typo fallbacks
    query_lower = re.sub(r'\b(this|last|current)\s+yea\b', r'\1 year', query_lower)
    query_lower = re.sub(r'\bpakage\b', 'package', query_lower)
    query_lower = re.sub(r'\bpackeg\b', 'package', query_lower)
    query = query_lower

    # 1. Run local spelling correction fast-path
    try:
        query = local_spelling_corrector(query)
    except Exception as e:
        logger.error(f"Local spelling correction failed: {e}")

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

    try:
        import asyncio

        from app.core.dependencies import get_coordinator_agent
        coordinator = get_coordinator_agent()
        admissions_agent = coordinator.agents.get("admissions")

        if admissions_agent:
            # Reusing the existing GeminiSynthesizer, which has Auto-Fallback to Ollama
            # if the Gemini API limit (429) is hit!
            domain_key = f"conversational_{lang}"
            response = await asyncio.to_thread(
                admissions_agent.synthesizer.synthesize,
                query=text,
                context_docs=[],
                domain=domain_key
            )

            if response and len(response) >= 5:
                result = response.strip().strip('"').strip("'")
                logger.info(f"make_conversational ({lang}) (Synthesizer): '{text[:50]}' -> '{result[:50]}'")
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
            "hi": "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकती हूँ?",
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

    # Pre-process native script phonetic variations for admissions / campus terms
    if detected_lang == "kn":
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಈಟಿ|ಇಟಿ|ಸಿಇಟಿ|ಕೆಸಿಇಟಿ)\s*(ಕೋಟ|ಕೋಟಾ|ಕೋಟೆಯ|ಕೋಟಾದ)($|\s|[^\w])', r'\g<1>KCET quota\g<4>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಈಟಿ|ಇಟಿ|ಸಿಇಟಿ|ಕೆಸಿಇಟಿ)\s*(ಅಡ್ಮಿಷನ್|ಅಡ್ಮಿಷನ್ಸ್|ದಾಖಲಾತಿ|ಪ್ರವೇಶ)($|\s|[^\w])', r'\g<1>KCET admission\g<4>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಡಾಕ್ಯುಮೆಂಟ್ಸ್|ದಾಖಲೆಗಳು|ದಾಖಲಾತಿಗಳು)\s*(ಬೇಕು|ಅಗತ್ಯ)($|\s|[^\w])', r'\g<1>documents required\g<4>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಕಟ್\s*ಆಫ್|ಕಟ್‌ಆಫ್|ಕಟಾಫ್)($|\s|[^\w])', r'\g<1>cutoff\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಫೀಸ್|ಶುಲ್ಕ|ಫೀ)($|\s|[^\w])', r'\g<1>fee structure\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಬಿ\.?\s*ಟೆಕ್|ಬಿಟೆಕ್)($|\s|[^\w])', r'\g<1>B.Tech\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(ಬಿ\.?\s*ಬಿ\.?\s*ಎ|ಬಿಬಿಎ)($|\s|[^\w])', r'\g<1>BBA\g<3>', clean_transcript)
    elif detected_lang == "hi":
        clean_transcript = re.sub(r'(^|\s|[^\w])(ब्बा|बीबीए|बी\s*बी\s*ए)($|\s|[^\w])', r'\g<1>BBA\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(बीटेक|बी\s*टेक)($|\s|[^\w])', r'\g<1>B.Tech\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(एमबीए|एम\s*बी\s*ए)($|\s|[^\w])', r'\g<1>MBA\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(बीसीए|बी\s*सी\s*ए)($|\s|[^\w])', r'\g<1>BCA\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(एमसीए|एम\s*सी\s*ए)($|\s|[^\w])', r'\g<1>MCA\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(केसीईटी|सीईटी)($|\s|[^\w])', r'\g<1>KCET\g<3>', clean_transcript)
        clean_transcript = re.sub(r'(^|\s|[^\w])(पेसैट|पैसैट)($|\s|[^\w])', r'\g<1>PESSAT\g<3>', clean_transcript)

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
        # Check for contextual pronouns (it, its, they, them, their, he, his, she, her)
        # Exclude existential clauses with 'there' (e.g. 'are there', 'is there', 'there is', 'there are')
        query_en_lower = query_en.lower()
        is_existential = bool(re.search(r'\b(is|are|was|were|will\s*be)\s+there\b|\bthere\s+(is|are|was|were)\b', query_en_lower))
        has_pronoun = bool(re.search(r'\b(it|its|they|them|their|he|his|she|her)\b', query_en_lower)) or (not is_existential and bool(re.search(r'\b(there)\b', query_en_lower)))
        if has_pronoun:
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
                            import asyncio
                            coordinator = get_coordinator_agent()
                            rewritten = await asyncio.to_thread(
                                coordinator.reformulate_query, query_en,
                                [{"query": t.get("content", ""), "response": ""} if t.get("role") == "user" else {"query": "", "response": t.get("content", "")} for t in history[-3:]]
                            )
                            if rewritten and rewritten.lower() != query_en_lower:
                                logger.info(f"Implicit Context Resolution: '{query_en}' -> '{rewritten}'")
                                query_en = rewritten
                        except Exception as e:
                            logger.error(f"Contextual rewrite failed: {e}")

    was_refined = False
    if outstanding:
        was_refined = True
        orig_q = outstanding.get("original_query") or ""
        clarification_q = outstanding.get("clarification_question")

        if orig_q.strip():
            try:
                import asyncio
                coordinator = get_coordinator_agent()
                history = [{"query": orig_q, "response": clarification_q or ""}]
                rewritten = await asyncio.to_thread(
                    coordinator.reformulate_query, query_en, history
                )
                if rewritten and rewritten.lower() != query_en.lower():
                    logger.info(f"Smart clarification merge: '{orig_q}' + '{query_en}' -> '{rewritten}'")
                    query_en = rewritten
                else:
                    query_en = f"{orig_q} {query_en}"
            except Exception as e:
                logger.error(f"Clarification rewrite failed: {e}")
                query_en = f"{orig_q} {query_en}"
        else:
            # Nothing to merge if original query was empty
            logger.info("Smart clarification merge skipped because original query was empty.")

        from app.core.session_store import update_session_metadata
        await update_session_metadata(session_id, {"outstanding_clarification": None})

        # Reload the updated session to get the latest DB metadata
        updated_session = await get_session(session_id)

    # Correct and normalize spelling/phrasing variations
    query_en = await correct_and_normalize_query(query_en, detected_lang)

    # Persist user turn
    await add_user_turn(session_id, clean_transcript)

    # 2. Fast-Path Router (Bypass LLM for common demo intents)
    fast_domain = get_strict_fast_path_domain(query_en)

    if fast_domain:
        logger.info(f"Fast-path matched for text query '{query_en}' -> {fast_domain}")
        target_domain = fast_domain
        refined_query = query_en
    else:
        coordinator = get_coordinator_agent()
        best_domain, confidence, reason, _ = coordinator.route(query_en)

        # Lightweight clarification mechanism for genuinely low-confidence cases
        is_complex = len(query_en.split()) > 5
        # Detect opinion/reputation queries about PES that don't need clarification
        is_opinion = any(w in query_en.lower() for w in ["good", "bad", "better", "best", "worst", "worth", "ranking", "ranked", "reputation"])
        if confidence < 0.45 and not was_refined and not is_complex and not is_opinion:
            logger.info(f"Low confidence routing ({confidence:.2f}): Triggering clarification.")
            question_en = coordinator.check_ambiguity(query_en)
            if not question_en:
                question_en = "Could you please clarify your question or specify what you are looking for?"

            import asyncio
            question_native = await asyncio.to_thread(translate_from_english, question_en, target_lang=detected_lang)
            await add_agent_turn(session_id, question_native)

            from app.core.session_store import update_session_metadata
            await update_session_metadata(
                session_id,
                {
                    "outstanding_clarification": {
                        "original_query": query_en,
                        "clarification_question": question_en,
                        "ambiguity_type": "LOW_CONFIDENCE",
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
                "ambiguity_type": "LOW_CONFIDENCE",
                "sources": [],
                "navigation": None,
                "language": detected_lang,
            }

        target_domain = best_domain if best_domain else "general"
        refined_query = query_en
        logger.info(f"CoordinatorAgent routed query to: {target_domain} (Confidence: {confidence:.2f})")

    nav_payload = None
    citations = []
    is_fallback = False

    if target_domain == "navigation":
        # Extract the location for the QR Code using LocationResolver directly, bypassing slow LLM
        try:
            from app.services.navigation_service import location_resolver, navigation_service
            top_loc = location_resolver.resolve(refined_query)

            if top_loc:
                from app.core.config import get_local_ip
                nav_id = await navigation_service.create_session(top_loc)
                nav_url = navigation_service.build_url(nav_id)
                matched_display_name = top_loc.get('matched_name', top_loc.get('name'))
                nav_payload = {
                    "navigation_id": nav_id,
                    "url": nav_url,
                    "destination_name": matched_display_name,
                    "building": top_loc.get("building"),
                    "floor": top_loc.get("floor"),
                    "room": top_loc.get("room"),
                    "kiosk_ip": get_local_ip()
                }

                # Construct real-time response programmatically
                room_text = f" (room {top_loc.get('room')})" if top_loc.get('room') else ""
                answer_en = f"The {matched_display_name} is located in {top_loc.get('building')} on Floor {top_loc.get('floor')}{room_text}. Please scan the QR code on the screen for step-by-step directions."
            else:
                answer_en = "I'm sorry, I could not find that location on the campus map. Please check the department directory."
                is_fallback = True
        except Exception as e:
            logger.error(f"Navigation QR code generation failed: {e}")
            answer_en = "I encountered an issue retrieving the navigation route."
            is_fallback = True
    elif target_domain == "announcements":
        try:
            from agents.autonomous.announcement_store import AnnouncementStore
            store = AnnouncementStore()
            active = store.get_active()

            stop_words = {
                "what", "show", "tell", "give", "latest", "recent", "about", "there", "have",
                "with", "this", "that", "from", "announcement", "announcements", "notice",
                "notices", "updates", "any", "are", "the", "for", "and", "can", "please"
            }
            raw_words = [
                w for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', refined_query.lower()).split()
                if len(w) >= 3 and w not in stop_words
            ]
            query_words = set(raw_words + [w.rstrip('s') for w in raw_words if len(w) > 4])
            matches = []
            if query_words:
                for a in active:
                    title_lower = a.get("title", "").lower()
                    body_lower = a.get("body", "").lower()
                    score = sum(4 for w in query_words if w in title_lower) + sum(1 for w in query_words if w in body_lower)
                    if score > 0:
                        matches.append((score, a))
                matches.sort(key=lambda x: x[0], reverse=True)
                relevant = [m[1] for m in matches[:5]]
            else:
                relevant = active[:5]

            if relevant:
                lines = ["Here are the latest announcements from PESU Academy:\n"]
                for idx, a in enumerate(relevant, 1):
                    posted = a.get("posted_date", "").replace("Date: ", "").strip()
                    date_str = f" ({posted})" if posted else ""
                    title = a.get("title", "Announcement")
                    lines.append(f"{idx}. **{title}**{date_str}")
                    body = a.get("body", "")
                    if "Links & Attachments:" in body:
                        links_part = body.split("Links & Attachments:")[1].strip()
                        lines.append(f"   {links_part}")
                    elif len(body) > len(title) + 5:
                        snippet = body.replace("\n", " ").strip()[:140]
                        lines.append(f"   {snippet}...")
                answer_en = "\n".join(lines)
                is_fallback = False
            else:
                answer_en = "There are currently no active announcements matching your query on PESU Academy. Please check the PESU Academy student portal."
                is_fallback = False
        except Exception as e:
            logger.error(f"Failed to fetch live announcements: {e}")
            answer_en = "I encountered an issue retrieving the latest announcements from PESU Academy."
            is_fallback = True
    else:
        coordinator = get_coordinator_agent()
        import asyncio

        full_answer = await asyncio.to_thread(
            coordinator.answer, refined_query, target_domain=target_domain
        )
        answer_en = _clean_agent_answer(full_answer)
        is_fallback = _is_fallback_answer(answer_en)

        # Contact-aware enrichment: if user asks for contact info, inject structured data
        contact_keywords = ["contact", "phone", "email", "call", "reach out", "get in touch"]
        if any(kw in refined_query.lower() for kw in contact_keywords):
            try:
                from config.contact_config import get_specific_contact
                contact = get_specific_contact(refined_query, domain=target_domain)
                contact_text = (
                    f"\n\nFor further assistance, contact the {contact['office_name']}:\n"
                    f"Email: {contact['email']}\n"
                    f"Phone: {contact['phone']}\n"
                    f"Location: {contact['location']}"
                )
                # If the answer is a fallback, replace it entirely with contact info
                if is_fallback:
                    answer_en = (
                        f"For your query, please contact the {contact['office_name']}.\n\n"
                        f"Email: {contact['email']}\n"
                        f"Phone: {contact['phone']}\n"
                        f"Location: {contact['location']}\n"
                        f"Website: {contact['website']}"
                    )
                    is_fallback = False
                else:
                    answer_en = answer_en.rstrip() + contact_text
            except Exception as e:
                logger.warning(f"Contact enrichment failed: {e}")

    if is_fallback:
        if not was_refined:
            # Evidence is not clear/sufficient, question back the user for clarification first
            question_en = "I'm sorry, I couldn't find clear information on that. Could you please provide more details or specify what you are looking for?"

            import asyncio
            question_native = await asyncio.to_thread(translate_from_english, question_en, target_lang=detected_lang)
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
    answer_native = ensure_clickable_links(answer_native)
    await add_agent_turn(session_id, answer_native)

    response_text = answer_native
    ambiguity_type = "CLEAR"
    domain = target_domain

    # Clean TTS text so the speaker does not read raw URLs or markdown brackets
    tts_text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", answer_native)
    tts_text = re.sub(r"https?://[^\s]+", "", tts_text)
    tts_text = re.sub(r"[*_#`]", "", tts_text)
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
        # Suppress verbose DB logging errors when postgres is intentionally offline
        if "[Errno 10061]" not in str(db_e) and "Connection refused" not in str(db_e):
            logger.warning(f"Background DB logging warning: {db_e}")

    return result
