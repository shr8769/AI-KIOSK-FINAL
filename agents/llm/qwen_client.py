# qwen_client.py
# Client for interacting with local Qwen3-8B model via Ollama with Gemini fallback.

import os
import json
import urllib.request
import urllib.error
import logging
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
        
    def is_ollama_available(self) -> bool:
        """
        Checks if the Ollama service is running and has the configured model available.
        """
        url = f"{self.ollama_url}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as response:
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
            logger.warning(f"Ollama service check failed: {e}")
            return False
        return False

    def generate(self, prompt: str) -> str:
        """
        Generates text using the Qwen3-8B model via Ollama.
        Falls back to Gemini synthesizer if any error occurs.
        """
        # First check if degraded or unavailable
        if self.is_degraded:
            return self._fallback_generate(prompt)

        if not self.is_ollama_available():
            logger.warning("Ollama or Qwen3-8B is unavailable. Falling back to Gemini synthesizer.")
            return self._fallback_generate(prompt)

        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10.0) as response:
                if response.status == 200:
                    res_data = json.loads(response.read().decode("utf-8"))
                    answer = res_data.get("response", "").strip()
                    if answer:
                        logger.info(f"Successfully generated answer using local model {self.model_name}")
                        return answer
                    else:
                        raise ValueError("Ollama returned empty response.")
                else:
                    raise urllib.error.HTTPError(url, response.status, "HTTP error", response.headers, None)
        except Exception as e:
            logger.error(f"Error during Ollama Qwen generation: {e}. Marking Qwen client degraded and falling back to Gemini.")
            self.is_degraded = True
            return self._fallback_generate(prompt)

    def _fallback_generate(self, prompt: str) -> str:
        """
        Executes generation using Gemini client.
        """
        if getattr(self.fallback_synthesizer, "is_degraded", False):
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
            logger.critical(f"Gemini fallback generation failed: {e}")
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                self.fallback_synthesizer.is_degraded = True
            return None
