# VidyaSahayak System Audit & Capability Discovery
*Date:* June 23, 2026
*Role:* Principal Software Architect

## Executive Summary

The VidyaSahayak architecture exhibits a sophisticated, multi-layered design. The foundational structure for the AI Kiosk is in place, featuring an event-driven hardware sensor layer, a dynamic React frontend, and a multi-agent RAG backend. 

- **Overall Readiness Score:** 7.5 / 10
- **MVP Readiness:** 90% (Pending deployment infrastructure and physical testing)
- **Production Readiness:** 60% (Requires optimization, streaming audio, and cultural localization)

The system gracefully handles fallback scenarios (e.g., local Ollama fallback if Gemini fails, in-memory store if Redis is missing, FAQ matching if ChromaDB is empty). However, it currently relies heavily on generic translation APIs rather than native LLM language generation, and the voice pipeline operates in half-duplex (chunked) mode rather than true real-time streaming.

---

## Feature Matrix

| Feature | Status | Ready? | Notes |
| ------- | ------ | ------ | ----- |
| **Edge Vision Detection** | Working | ✅ | YOLO11n integration functional. Decoupled from API via HTTP events. |
| **Voice Interaction** | Working | ✅ | Uses WebSockets. Half-duplex chunked transmission. |
| **Barge-in / Interrupt** | Partial | ⚠️ | Frontend halts playback, but backend does not abort generation. |
| **Multilingual (KN, HI)** | Working | ⚠️ | Functional but relies on Google Translate (Textbook translations). |
| **RIAR Pipeline** | Working | ✅ | Triggers clarifications for ambiguous queries. Requires Gemini Key. |
| **Multi-Agent RAG** | Working | ✅ | Coordinator routes to 6 domains. |
| **QR Mobile Handoff** | Working | ✅ | Dynamic routing, session TTLs, and React QR rendering functional. |
| **Local LLM Fallback** | Working | ✅ | `qwen3:latest` (Ollama) acts as a robust fallback for Gemini. |
| **Real-time Streaming** | Missing | ❌ | Audio is sent in complete chunks. Streaming TTS/ASR is not yet implemented. |

---

## System Architecture Diagram

```mermaid
flowchart TD
    subgraph Edge Hardware
        C[Camera] -->|Frames| YOLO[Presence Monitor YOLO11n]
        YOLO -->|HTTP POST| BE_Events[/api/v1/events/presence]
    end

    subgraph Frontend Kiosk
        BE_Events -.->|WS Push| UI_State[React Kiosk UI]
        Mic[Microphone] -->|Base64 Chunks| WS_Client[WebSocket Client]
        UI_State -->|QR Code| MobileHandoff[Next.js Mobile Route]
    end

    subgraph Backend Pipeline
        WS_Client <-->|ws://.../session| WS_Router[session_ws.py]
        
        WS_Router --> ASR[Faster-Whisper]
        ASR --> Trans_IN[GoogleTranslator: Native -> EN]
        Trans_IN --> RIAR[RIAR Pipeline: Ambiguity Check]
        
        RIAR --> Coord[Coordinator Agent]
        Coord --> Domain[Domain Agents e.g., Admissions, Navigation]
        Domain --> DB[(ChromaDB + FAQ JSON)]
        Domain --> Syn[GeminiSynthesizer / Ollama Qwen3]
        
        Syn --> Trans_OUT[GoogleTranslator: EN -> Native]
        Trans_OUT --> TTS[Cartesia / gTTS]
        TTS -->|Audio URL| WS_Router
    end
```

---

## Working Features
*(Demonstrable today without writing new code)*

1. **End-to-End Voice Chat:** A user can walk up, be detected, speak in English, and receive an AI-generated vocal response.
2. **Domain Routing:** The system can accurately route queries to `Admissions`, `Academics`, `Navigation`, etc.
3. **QR Navigation Handoff:** If a user asks "Where is the Physics Lab?", the kiosk provides a QR code. Scanning it opens a mobile web view with building/floor details.
4. **Hardware Decoupling:** The `week2_vision_demo.py` successfully runs a standalone YOLO process that pings the backend.
5. **Resilient Fallbacks:** If Redis fails, `navigation_service.py` falls back to an in-memory dictionary. If Gemini API fails, `gemini_rag.py` invokes local Ollama. If ChromaDB is empty, `base_agent.py` falls back to keyword-matching against `faq.json`.

---

## Partially Working Features

1. **Barge-in:** The frontend UI implements a "Barge-in" button that halts audio playback and sends an `interrupt` WebSocket message. However, the backend logs note: `"In Phase 2 (streaming), we would cancel the active generation task here."` Currently, the backend wastes compute finishing the abandoned generation.
2. **Multilingual Generation:** Queries in Kannada or Hindi are translated to English via `GoogleTranslator`, processed in English, and the English answer is translated back to Kannada/Hindi. This results in textbook, formal translations rather than culturally natural conversational language.
3. **Session Persistence:** SQLite persists session history, but returning-user face recognition memory (Objective 4) is not yet wired to context injection.

---

## Mocked / Stubbed Features

1. **Camera Frames over WS:** In `session_ws.py`, the `frame` WebSocket message type instantly returns a stubbed `{"person_detected": True, "confidence": 0.91}` payload. (Actual detection relies on the separate `PresenceMonitor` microservice).
2. **Campus Map Assets:** The Next.js mobile navigation page uses a static/placeholder `CampusMap.tsx` component rather than a real interactive GIS map.
3. **Real-Time Duplex:** The system mimics real-time interaction by aggressively chunking audio, but does not use true streaming WebRTC or byte-stream TTS.

---

## Critical Bottlenecks

1. **Event Loop Blocking (Resolved):** Previously, synchronous LLM calls blocked the ASGI event loop, dropping WebSockets. This was patched via `asyncio.to_thread`.
2. **Translation Latency:** Using GoogleTranslator twice per turn adds ~400-800ms of latency before and after the LLM generation step.
3. **Ollama Hardware Dependency:** When Gemini is disabled, `qwen3:latest` runs locally. Without a dedicated GPU, response times can easily exceed 5 seconds, severely degrading the UX.

---

## Missing Objective Coverage

| Objective | Status | Findings |
| :--- | :--- | :--- |
| **Obj 1: Intelligent Detection & Engagement** | **70%** | Proximity detection works. Facial recognition for returning users is missing. |
| **Obj 2: Multilingual Conversational Intel** | **80%** | RAG and LLM integration work. Native multilingual generation is bypassed via external translation. |
| **Obj 3: University System Integration** | **40%** | Campus Navigation is implemented (via QR handoff). Student Information System, Assessment, and Research portals are not actively wired to real APIs (using static JSON/RAG). |
| **Obj 4: Context-Aware Assistance** | **60%** | Multi-turn memory works within a session. Long-term returning user context is missing. |

---

## Deployment Readiness

**Can this system be deployed today?**
**No.** It can be used for an impressive controlled MVP demo, but is not production-ready for an unmonitored university hallway.

**Blockers:**
1. Next.js production build required (just successfully compiled in the audit).
2. Requires a dedicated GPU host for YOLO and Ollama, or guaranteed uptime for Google APIs.
3. No monitoring/observability dashboard for kiosk fleet management.
4. Edge Sensor script (`detection/main.py`) needs to be containerized or run as a SystemD daemon to ensure it recovers from camera hardware disconnects.

**Recommended Fixes before deployment:**
- Containerize the `frontend`, `backend`, and `detection` modules via `docker-compose`.
- Implement true LLM-native multilingual prompts (passing `language: kannada` to Gemini) instead of relying on `GoogleTranslator`.

---

## Recommended MVP Freeze Scope (v1.0.0-MVP)

**Include in v1.0.0:**
- YOLO Presence Detection (Single Camera)
- English + Kannada + Hindi (using the current translation pipeline)
- Navigation QR Handoff (with placeholder maps and static directions)
- Admissions & Academics RAG (using static FAQ JSON and ChromaDB)
- Fallback to Local Ollama

**Postpone to v1.1.0 (Do NOT build now):**
- True Streaming Full-Duplex Audio (WebRTC)
- Facial Recognition for Returning Users
- Live API integration with the Student Information System
- Interactive SLAM/GIS Campus Maps
