"""
Mock implementations of every service mapping to our API contracts.
"""

from app.models.schemas import (
    ASRRequest,
    ASRResponse,
    ClarifyRequest,
    ClarifyResponse,
    DetectRequest,
    DetectResponse,
    RAGRequest,
    RAGResponse,
    RetrievedChunkModel,
    RIARRequest,
    RIARResponse,
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
            greeting_text="Hello! Welcome to PES University. How can I help you today?",
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


class RIARService:
    async def classify(self, request: RIARRequest) -> RIARResponse:
        query = request.query.lower()
        
        # Keyword-based domain classification
        domain = "general"
        if any(kw in query for kw in ["admission", "apply", "seat", "seats", "register", "registration", "pessat", "eligibility", "cut-off", "cutoff"]):
            domain = "admissions"
        elif any(kw in query for kw in ["course", "courses", "syllabus", "exam", "exams", "marks", "credits", "credit", "class", "classes", "semester", "semesters", "academics"]):
            domain = "academics"
        elif any(kw in query for kw in ["placement", "placements", "job", "jobs", "salary", "packages", "package", "recruit", "recruits", "recruiter", "recruiters", "company", "companies"]):
            domain = "placements"
        elif any(kw in query for kw in ["research", "phd", "project", "projects", "paper", "papers", "publication", "publications"]):
            domain = "research"
        elif any(kw in query for kw in ["hostel", "hostels", "scholarship", "scholarships", "library", "libraries", "sport", "sports", "facilities", "facility"]):
            domain = "student_services"
        elif any(kw in query for kw in ["where", "location", "locations", "map", "building", "buildings", "floor", "floors", "block", "blocks", "direction", "directions", "room", "rooms", "office", "offices", "toilet", "toilets", "canteen", "cafeteria", "cafetaria", "situated", "located", "find", "reach"]):
            domain = "navigation"

        return RIARResponse(
            session_id=request.session_id,
            ambiguity_detected=False,
            ambiguity_score=0.1,
            ambiguity_type="CLEAR",
            refined_query=request.query,
            domain=domain,
            routing_confidence=0.9,
            requires_clarification=False,
        )

    async def clarify(self, request: ClarifyRequest) -> ClarifyResponse:
        return ClarifyResponse(
            session_id=request.session_id,
            refined_query=f"{request.original_query} -> {request.clarification_response}",
            domain="admissions",
            routing_confidence=0.9,
            ready_for_rag=True,
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
        
        answers = {
            "admissions": "For admissions, PES University conducts PESSAT. Registration details, eligibility criteria, and fee structures can be found on our admissions portal.",
            "academics": "Our academic program is designed to be rigorous and modern. Course structures, syllabi, exam schedules, and credit structures are available on the student portal.",
            "placements": "PES University has an excellent placement record, with top companies visiting our campus annually. Average salary packages range between 8 to 12 LPA.",
            "research": "PES University is heavily invested in research with multiple research centers and PhD programs across engineering and sciences.",
            "student_services": "Student facilities include extensive libraries, sports complex, state-of-the-art hostels, and various technical and cultural clubs.",
            "navigation": "To navigate the campus, please follow the main walkway. The admissions office is located in the main Golden Jubilee Block on the ground floor.",
            "general": "Thank you for asking. PES University offers world-class education with courses in Engineering, Medicine, Management, and Law."
        }
        
        # Tailor answer slightly with query terms if possible
        answer = answers.get(domain, answers["general"])
        
        # Optional: rule-based custom answers for specific common queries
        query_lower = query.lower()
        if "where" in query_lower and "office" in query_lower:
            answer = "The admissions office is located on the ground floor of the Golden Jubilee Block, right next to the entrance lobby."
        elif any(kw in query_lower for kw in ["canteen", "cafeteria", "cafetaria"]):
            answer = "The main campus cafeteria is situated next to the central library complex, near the football ground. It serves snacks, meals, and beverages from 8:00 AM to 8:00 PM."
        elif "pessat" in query_lower:
            answer = "PESSAT is the PES Scholastic Aptitude Test. You can register online at the official PESSAT website. Eligibility requires 60% aggregate in Physics, Chemistry, and Math."
        elif "placement" in query_lower or "placements" in query_lower:
            answer = "Over 100 top companies recruit from PES University every year, including companies like Microsoft, Amazon, and Cisco. The average package is 8 to 12 LPA, and the highest package last year exceeded 40 LPA."

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
riar_service = RIARService()
route_service = RouteService()
rag_service = RAGService()
tts_service = TTSService()
