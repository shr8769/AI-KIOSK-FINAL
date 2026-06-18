# qwen_client.py
# Client for interacting with local Qwen3-8B model via Ollama with Gemini fallback.

import os
import json
import urllib.request
import urllib.error
import logging
import traceback
import time
from config import llm_config
from agents.domain.gemini_rag import GeminiSynthesizer

logger = logging.getLogger(__name__)

class QwenClient:
    """
    Client wrapper for local Qwen3-8B model running via Ollama.
    Automatically falls back to Gemini if Ollama is unavailable or errors out.
    """
    def __init__(self):
        self.ollama_url = llm_config.OLLAMA_URL
        self.model_name = llm_config.OLLAMA_MODEL
        self.fallback_synthesizer = GeminiSynthesizer(model_name=llm_config.GEMINI_MODEL)
        self.is_degraded = False
        
        # Perform warmup request to load model into memory
        if self.is_ollama_available():
            logger.info(f"Ollama is available. Performing warmup request for model {self.model_name}...")
            try:
                # Prompt to warmup/load the model into memory
                payload = {
                    "model": self.model_name,
                    "prompt": "warmup",
                    "stream": False,
                    "options": {
                        "num_predict": 1
                    }
                }
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.ollama_url}/api/generate",
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                # Keep timeout short for warmup, 30s is more than enough to load a model
                with urllib.request.urlopen(req, timeout=30.0) as response:
                    if response.status == 200:
                        logger.info("Warmup request completed successfully.")
            except Exception as e:
                logger.warning(f"Warmup request failed: {e}. Exception trace:\n{traceback.format_exc()}")
        else:
            logger.warning(f"Ollama or model {self.model_name} is not available at startup. Warmup bypassed.")
        
    def is_ollama_available(self) -> bool:
        """
        Checks if the Ollama service is running and has the configured model available.
        """
        url = f"{self.ollama_url}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    models = [m.get("name") for m in data.get("models", [])]
                    # Check if model name matches (e.g., qwen3:8b)
                    # We also accept substring matches to handle tag variants
                    for m in models:
                        if self.model_name in m or m in self.model_name:
                            return True
                    logger.warning(f"Ollama is running, but model '{self.model_name}' was not found in tags: {models}")
                    return False
        except Exception as e:
            logger.warning(f"Ollama service check failed: {e}. Exception stack trace:\n{traceback.format_exc()}")
            return False
        return False

    def generate(self, prompt: str) -> str:
        """
        Generates text using the Qwen3-8B model via Ollama.
        Falls back to Gemini synthesizer if any error occurs.
        """
        # First check if degraded or unavailable
        if self.is_degraded:
            logger.info("Qwen client is marked degraded. Using Gemini fallback.")
            return self._fallback_generate(prompt)

        if not self.is_ollama_available():
            logger.warning("Ollama or Qwen3-8B is unavailable. Falling back to Gemini synthesizer.")
            # Automatically use Gemini fallback
            return self._fallback_generate(prompt)

        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        
        start_time = time.perf_counter()
        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            # Increased timeout to 120.0 seconds
            with urllib.request.urlopen(req, timeout=120.0) as response:
                latency = time.perf_counter() - start_time
                if response.status == 200:
                    res_data = json.loads(response.read().decode("utf-8"))
                    answer = res_data.get("response", "").strip()
                    
                    # Log details
                    prompt_tokens = res_data.get("prompt_eval_count", 0)
                    response_tokens = res_data.get("eval_count", 0)
                    total_tokens = prompt_tokens + response_tokens
                    
                    logger.info(
                        f"Successfully generated answer using local model: {self.model_name} | "
                        f"Latency: {latency:.4f}s | "
                        f"Tokens: {total_tokens} (Prompt: {prompt_tokens}, Resp: {response_tokens})"
                    )
                    
                    if answer:
                        return answer
                    else:
                        raise ValueError("Ollama returned empty response.")
                else:
                    raise urllib.error.HTTPError(url, response.status, "HTTP error", response.headers, None)
        except Exception as e:
            latency = time.perf_counter() - start_time
            stack_trace = traceback.format_exc()
            logger.error(
                f"Error during Ollama Qwen generation: {e} | "
                f"Model: {self.model_name} | "
                f"Latency so far: {latency:.4f}s. "
                f"Marking Qwen client degraded and falling back to Gemini.\n"
                f"Stack Trace:\n{stack_trace}"
            )
            self.is_degraded = True
            return self._fallback_generate(prompt)

    def _fallback_generate(self, prompt: str) -> str:
        """
        Executes generation using Gemini client.
        """
        if getattr(self.fallback_synthesizer, "is_degraded", False):
            logger.warning("Gemini fallback synthesizer is degraded. Returning None.")
            return None

        if not self.fallback_synthesizer.client:
            logger.critical("Gemini fallback client is also unavailable. Returning None.")
            return None
            
        try:
            response = self.fallback_synthesizer.client.models.generate_content(
                model=self.fallback_synthesizer.model_name,
                contents=prompt,
            )
            if response.text:
                logger.info(f"Successfully synthesized response using fallback Gemini model {self.fallback_synthesizer.model_name}")
                return response.text.strip()
            return None
        except Exception as e:
            logger.critical(f"Gemini fallback generation failed: {e}. Traceback:\n{traceback.format_exc()}")
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                self.fallback_synthesizer.is_degraded = True
            return None
