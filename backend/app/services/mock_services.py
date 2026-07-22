"""
Mock implementations of every service mapping to our API contracts.
"""

from app.models.schemas import (
    ASRRequest,
    ASRResponse,
    DetectRequest,
    DetectResponse,
    RAGRequest,
    RAGResponse,
    RetrievedChunkModel,
    RouteRequest,
    RouteResponse,
    TTSRequest,
    TTSResponse,
)


class DetectionService:
    async def detect(self, session_id: str, request: DetectRequest) -> DetectResponse:
        return DetectResponse(
            session_id=session_id,
            action="session_created",
            greeting_text="Hello! Welcome to PES University. Please tell me which language you would like to interact with: English, Kannada, or Hindi?",
            greeting_audio_url="/static/audio/greeting_en.mp3",
            language_prompt="Please speak in English, Kannada, or Hindi.",
        )


class ASRService:
    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        return ASRResponse(
            session_id=request.session_id,
            turn_id=request.turn_id,
            transcript="Where is the admissions office?",
            detected_language="en",
            confidence=0.95,
            duration_ms=3000,
            latency_ms=480,
        )


class RouteService:
    async def route(self, request: RouteRequest) -> RouteResponse:
        agent_name = f"Mock{request.domain.replace('_', ' ').title().replace(' ', '')}Agent"
        return RouteResponse(
            session_id=request.session_id,
            agent=agent_name,
            domain=request.domain,
            retrieved_chunks=[
                RetrievedChunkModel(
                    chunk_id="mock_chunk_1",
                    source="mock_source.md",
                    text=f"Mock {request.domain} information",
                    relevance_score=0.9,
                )
            ],
            context_window=f"Mock {request.domain} information context",
            retrieval_latency_ms=100,
        )


class RAGService:
    async def generate(self, request: RAGRequest) -> RAGResponse:
        query = request.query
        domain = request.domain
        lang = (request.language or "en").lower()

        # Multilingual database
        answers_db = {
            "en": {
                "admissions": "For admissions, PES University conducts PESSAT. Registration details, eligibility criteria, and fee structures can be found on our admissions portal.",
                "academics": "Our academic program is designed to be rigorous and modern. Course structures, syllabi, exam schedules, and credit structures are available on the student portal.",
                "placements": "PES University has an excellent placement record, with top companies visiting our campus annually. Average salary packages range between 8 to 12 LPA.",
                "research": "PES University is heavily invested in research with multiple research centers and PhD programs across engineering and sciences.",
                "student_services": "Student facilities include extensive libraries, sports complex, state-of-the-art hostels, and various technical and cultural clubs.",
                "navigation": "To navigate the campus, please follow the main walkway. The admissions office is located in the main Golden Jubilee Block on the ground floor.",
                "general": "Thank you for asking. PES University offers world-class education with courses in Engineering, Medicine, Management, and Law.",
            },
            "kn": {
                "admissions": "ಪ್ರವೇಶಾತಿಗಾಗಿ, ಪಿಇಎಸ್ ವಿಶ್ವವಿದ್ಯಾಲಯವು ಪೆಸ್ಸಾಟ್ (PESSAT) ಪರೀಕ್ಷೆಯನ್ನು ನಡೆಸುತ್ತದೆ. ನೋಂದಣಿ ವಿವರಗಳು, ಅರ್ಹತಾ ಮಾನದಂಡಗಳು ಮತ್ತು ಶುಲ್ಕದ ವಿವರಗಳನ್ನು ನಮ್ಮ ಪ್ರವೇಶಾತಿ ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ಕಾಣಬಹುದು.",
                "academics": "ನಮ್ಮ ಶೈಕ್ಷಣಿಕ ಕಾರ್ಯಕ್ರಮವು ಅತ್ಯಂತ ಸುಧಾರಿತವಾಗಿದೆ. ಕೋರ್ಸ್ ವಿವರಗಳು, ಪಠ್ಯಕ್ರಮ, ಪರೀಕ್ಷಾ ವೇಳಾಪಟ್ಟಿಗಳು ಮತ್ತು ಕ್ರೆಡಿಟ್ ವಿವರಗಳು ವಿದ್ಯಾರ್ಥಿ ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ಲಭ್ಯವಿವೆ.",
                "placements": "ಪಿಇಎಸ್ ವಿಶ್ವವಿದ್ಯಾಲಯವು ಅತ್ಯುತ್ತಮ ಉದ್ಯೋಗ ಅವಕಾಶಗಳ (ಪ್ಲೇಸ್‌ಮೆಂಟ್ಸ್) ದಾಖಲೆಯನ್ನು ಹೊಂದಿದೆ. ಪ್ರತಿ ವರ್ಷ ಪ್ರಮುಖ ಕಂಪನಿಗಳು ನಮ್ಮ ಕ್ಯಾಂಪಸ್‌ಗೆ ಭೇಟಿ ನೀಡುತ್ತವೆ. ಸರಾಸರಿ ಸಂಬಳದ ಪ್ಯಾಕೇಜ್ ವರ್ಷಕ್ಕೆ 8 ರಿಂದ 12 ಲಕ್ಷ ರೂಪಾಯಿಗಳಿರುತ್ತದೆ.",
                "research": "ಪಿಇಎಸ್ ವಿಶ್ವವಿದ್ಯಾಲಯವು ಸಂಶೋಧನೆಗೆ ಹೆಚ್ಚಿನ ಪ್ರೋತ್ಸಾಹ ನೀಡುತ್ತದೆ. ನಮ್ಮಲ್ಲಿ ಹಲವು ಸಂಶೋಧನಾ ಕೇಂದ್ರಗಳು ಮತ್ತು ಪಿಎಚ್‌ಡಿ ಕಾರ್ಯಕ್ರಮಗಳಿವೆ.",
                "student_services": "ವಿದ್ಯಾರ್ಥಿ ಸೌಲಭ್ಯಗಳಲ್ಲಿ ಗ್ರಂಥಾಲಯಗಳು, ಕ್ರೀಡಾ ಸಂಕೀರ್ಣಗಳು, ಸುಸಜ್ಜಿತ ಹಾಸ್ಟೆಲ್‌ಗಳು ಮತ್ತು ವಿವಿಧ ತಾಂತ್ರಿಕ ಹಾಗೂ ಸಾಂಸ್ಕೃತಿಕ ಕ್ಲಬ್‌ಗಳು ಸೇರಿವೆ.",
                "navigation": "ಕ್ಯಾಂಪಸ್‌ನಲ್ಲಿ ಸಂಚರಿಸಲು ದಯವಿಟ್ಟು ಮುಖ್ಯ ನಡಿಗೆಯ ಹಾದಿಯನ್ನು ಅನುಸರಿಸಿ. ಪ್ರವೇಶಾತಿ ಕಚೇರಿಯು ಮುಖ್ಯ ಗೋಲ್ಡನ್ ಜುಬಿಲಿ ಬ್ಲಾಕ್‌ನ ನೆಲಮಹಡಿಯಲ್ಲಿದೆ.",
                "general": "ಕೇಳಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ಪಿಇಎಸ್ ವಿಶ್ವವಿದ್ಯಾಲಯವು ಎಂಜಿನಿಯರಿಂಗ್, ವೈದ್ಯಕೀಯ, ನಿರ್ವಹಣೆ ಮತ್ತು ಕಾನೂನು ಕೋರ್ಸ್‌ಗಳೊಂದಿಗೆ ವಿಶ್ವದರ್ಜೆಯ ಶಿಕ್ಷಣವನ್ನು ನೀಡುತ್ತದೆ.",
            },
            "hi": {
                "admissions": "प्रवेश के लिए, पीईएस विश्वविद्यालय पेसैट (PESSAT) परीक्षा आयोजित करता है। पंजीकरण विवरण, पात्रता मानदंड और शुल्क संरचना हमारे प्रवेश पोर्टल पर देखी जा सकती है।",
                "academics": "हमारा शैक्षणिक कार्यक्रम आधुनिक और व्यापक है। पाठ्यक्रम संरचना, परीक्षा कार्यक्रम और क्रेडिट विवरण छात्र पोर्टल पर उपलब्ध हैं।",
                "placements": "पीईएस विश्वविद्यालय का प्लेसमेंट रिकॉर्ड उत्कृष्ट है। प्रमुख कंपनियां सालाना हमारे परिसर का दौरा करती हैं। औसत वेतन पैकेज 8 से 12 लाख प्रति वर्ष के बीच है।",
                "research": "पीईएस विश्वविद्यालय अनुसंधान में काफी निवेश करता है, जिसमें इंजीनियरिंग और विज्ञान में कई अनुसंधान केंद्र और पीएचडी कार्यक्रम हैं।",
                "student_services": "छात्र सुविधाओं में पुस्तकालय, खेल परिसर, आधुनिक छात्रावास और विभिन्न तकनीकी और सांस्कृतिक क्लब शामिल हैं।",
                "navigation": "परिसर में नेविगेट करने के लिए मुख्य मार्ग का अनुसरण करें। प्रवेश कार्यालय मुख्य गोल्डन जुबली ब्लॉक के भूतल पर स्थित है।",
                "general": "पूछने के लिए धन्यवाद। पीईएस विश्वविद्यालय इंजीनियरिंग, चिकित्सा, प्रबंधन और कानून के पाठ्यक्रमों के साथ विश्व स्तरीय शिक्षा प्रदान करता है।",
            },
        }

        # Get language specific dictionary, fallback to English
        lang_db = answers_db.get(lang, answers_db["en"])
        answer = lang_db.get(domain, lang_db["general"])

        # Custom rule-based queries translation
        query_lower = query.lower()
        if (
            "where" in query_lower
            and "office" in query_lower
            or "ಕಚೇರಿ" in query_lower
            or "कार्यालय" in query_lower
            or ("ಅಡ್ಮಿಷನ್" in query_lower and "ಎಲ್ಲಿದೆ" in query_lower)
            or "praveshathi" in query_lower
            or "ಪ್ರವೇಶ" in query_lower
        ):
            if lang == "kn":
                answer = "ಪಿಇಎಸ್ ವಿಶ್ವವಿದ್ಯಾಲಯದಲ್ಲಿ ಪ್ರವೇಶಾತಿಗಾಗಿ ಪೆಸ್ಸಾಟ್ (PESSAT) ಪ್ರವೇಶ ಪರೀಕ್ಷೆ ಬರೆಯಬೇಕು. ಹೆಚ್ಚಿನ ವಿವರಗಳಿಗಾಗಿ ಗೋಲ್ಡನ್ ಜುಬಿಲಿ ಬ್ಲಾಕ್‌ನ ನೆಲಮಹಡಿಯಲ್ಲಿರುವ ಪ್ರವೇಶಾತಿ ಕಚೇರಿಯನ್ನು ಸಂಪರ್ಕಿಸಿ."
            elif lang == "hi":
                answer = "पीईएस विश्वविद्यालय में प्रवेश के लिए आपको पेसैट (PESSAT) परीक्षा देनी होगी। अधिक जानकारी के लिए भूतल पर स्थित प्रवेश कार्यालय से संपर्क करें।"
            else:
                answer = "For admissions at PES University, you need to take the PESSAT exam. For details, contact the admissions office on the ground floor of the Golden Jubilee Block."
        elif any(
            kw in query_lower
            for kw in ["canteen", "cafeteria", "cafetaria", "ಊಟ", "ಕ್ಯಾಂಟೀನ್", "कैंटीन", "कैफेटेरिया"]
        ):
            if lang == "kn":
                answer = "ಮುಖ್ಯ ಕ್ಯಾಂಪಸ್ ಕೆಫೆಟೇರಿಯಾ ಕೇಂದ್ರ ಗ್ರಂಥಾಲಯದ ಪಕ್ಕದಲ್ಲಿದೆ, ಫುಟ್‌ಬಾಲ್ ಮೈದಾನದ ಹತ್ತಿರ. ಇದು ಬೆಳಿಗ್ಗೆ 8:00 ರಿಂದ ರಾತ್ರಿ 8:00 ರವರೆಗೆ ತೆರೆದಿರುತ್ತದೆ."
            elif lang == "hi":
                answer = "मुख्य परिसर कैंटीन केंद्रीय पुस्तकालय परिसर के बगल में, फुटबॉल मैदान के पास स्थित है। यह सुबह 8:00 बजे से रात 8:00 बजे तक खुली रहती है।"
            else:
                answer = "The main campus cafeteria is situated next to the central library complex, near the football ground. It serves snacks, meals, and beverages from 8:00 AM to 8:00 PM."
        elif (
            "placement" in query_lower
            or "placements" in query_lower
            or "ಕೆಲಸ" in query_lower
            or "ಪ್ಲೇಸ್‌ಮೆಂಟ್" in query_lower
            or "प्लेसमेंट" in query_lower
        ):
            if lang == "kn":
                answer = "ಪಿಇಎಸ್ ವಿಶ್ವವಿದ್ಯಾಲಯವು ಅತ್ಯುತ್ತಮ ಪ್ಲೇಸ್‌ಮೆಂಟ್ ಹೊಂದಿದ್ದು, ಮೈಕ್ರೋಸಾಫ್ಟ್, ಅಮೆಜಾನ್ ಮತ್ತು ಸಿಸ್ಕೋ ಕಂಪನಿಗಳು ಭೇಟಿ ನೀಡುತ್ತವೆ. ಸರಾಸರಿ ಪ್ಯಾಕೇಜ್ 8 ರಿಂದ 12 LPA ಆಗಿದೆ."
            elif lang == "hi":
                answer = "पीईएस विश्वविद्यालय में उत्कृष्ट प्लेसमेंट हैं, जिसमें माइक्रोसॉफ्ट, अमेज़ॅन और सिस्को जैसी कंपनियां शामिल हैं। औसत पैकेज 8 से 12 LPA है।"
            else:
                answer = "Over 100 top companies recruit from PES University every year, including Microsoft, Amazon, and Cisco. The average package is 8 to 12 LPA."

        return RAGResponse(
            session_id=request.session_id,
            answer=answer,
            citations=["pes_university_database.md"],
            model_used="mock_model",
            tokens_used=120,
            generation_latency_ms=250,
            confidence_score=0.95,
        )


class TTSService:
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        return TTSResponse(
            session_id=request.session_id,
            audio_url="/static/mock_response.mp3",
            duration_seconds=5.0,
            format="mp3",
            latency_ms=300,
        )


detection_service = DetectionService()
asr_service = ASRService()
route_service = RouteService()
rag_service = RAGService()
tts_service = TTSService()
