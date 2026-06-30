import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

class StartupState:
    ready: bool = False
    warming: bool = True
    errors: list[str] = []
    messages: list[str] = ["Initializing AI..."]
    metrics: Dict[str, Any] = {}

startup_state = StartupState()

def warmup_services():
    """Centralized warmup orchestration to avoid cold-starts on first user query."""
    overall_start = time.time()
    startup_state.messages.append("Loading Speech Engine...")
    logger.info("Starting backend service warmup...")

    # 1. Warm up ASR (Whisper)
    try:
        t0 = time.time()
        from app.services.speech.asr_service import asr_service
        asr_service.preload()
        asr_service.warmup_inference()
        startup_state.metrics["whisper_load_ms"] = int((time.time() - t0) * 1000)
        logger.info(f"Whisper warmup complete in {startup_state.metrics['whisper_load_ms']}ms")
    except Exception as e:
        logger.error(f"Whisper warmup failed: {e}")
        startup_state.errors.append(f"Whisper: {e}")

    # 2. Warm up RIAR Pipeline & Embeddings
    startup_state.messages.append("Loading Knowledge Base...")
    try:
        t0 = time.time()
        from app.core.dependencies import get_riar_pipeline
        pipeline = get_riar_pipeline()

        # We can simulate a dummy query to warm up the LLM, the embedding model, and the agent
        # (Skipped dummy query in local startup to avoid slow CPU inference delay)
        # try:
        #     pipeline.process_query("warmup_session", 1, "What is the fee structure?", "en", [])
        # except Exception as e:
        #     logger.warning(f"RIAR dummy query completed with expected exception during warmup: {e}")

        startup_state.metrics["riar_warmup_ms"] = int((time.time() - t0) * 1000)
        logger.info(f"RIAR Pipeline warmup complete in {startup_state.metrics['riar_warmup_ms']}ms")
    except Exception as e:
        logger.error(f"RIAR warmup failed: {e}")
        startup_state.errors.append(f"RIAR: {e}")

    # 3. Warm up Coordinator Agent
    try:
        t0 = time.time()
        from app.core.dependencies import get_coordinator_agent
        coordinator = get_coordinator_agent()
        # Warmup the coordinator by checking its initialization or running a simple dummy query
        # (Skipped dummy query in local startup to avoid slow CPU inference loop)
        # try:
        #     coordinator.answer("warmup_query")
        # except Exception as e:
        #     logger.warning(f"Coordinator dummy query completed with expected exception: {e}")

        startup_state.metrics["coordinator_warmup_ms"] = int((time.time() - t0) * 1000)
        logger.info(f"Coordinator warmup complete in {startup_state.metrics['coordinator_warmup_ms']}ms")
    except Exception as e:
        logger.error(f"Coordinator warmup failed: {e}")
        startup_state.errors.append(f"Coordinator: {e}")

    startup_state.metrics["total_startup_ms"] = int((time.time() - overall_start) * 1000)
    logger.info(f"All warmups complete. Total time: {startup_state.metrics['total_startup_ms']}ms")

    if startup_state.errors:
        logger.error(f"Startup completed with errors: {startup_state.errors}")
        startup_state.ready = False
    else:
        startup_state.ready = True
        startup_state.messages.append("Ready")

    startup_state.warming = False
