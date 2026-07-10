import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class GeminiSynthesizer:
    """
    A wrapper class to interface with Google's Gemini models for synthesizing
    retrieved context documents into natural language answers (RAG).
    Provides compatibility fallbacks if Google GenAI SDK or API keys are missing.
    Fallback to local Qwen (Ollama) is used if GEMINI_API_KEY is not set.
    """
    def __init__(self, api_key: str = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None
        self.ollama_client = None
        self.is_degraded = False
        self.degraded_at = 0.0
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Gemini client successfully with model {model_name}.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}. Falling back to local Ollama (qwen3:latest).")
                self._init_ollama()
        else:
            logger.info("GEMINI_API_KEY not found in environment. Initializing local Ollama (qwen3:latest) fallback.")
            self._init_ollama()

    def _init_ollama(self):
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("localhost", 11434))
            from langchain_ollama import ChatOllama
            self.ollama_client = ChatOllama(model="qwen3:latest")
            logger.info("Initialized local Ollama client successfully with model qwen3:latest.")
        except Exception as e:
            logger.warning(f"Ollama service is not running on localhost:11434 ({e}). RAG synthesis fallback will be unavailable.")
            self.ollama_client = None

    def synthesize(self, query: str, context_docs: list, domain: str) -> str:
        """
        Synthesizes an answer using the query and a list of context documents based on the domain prompt template.
        If Gemini is unavailable or errors out, falls back to local Ollama (Qwen) synthesis.
        If both are unavailable, returns None.
        """
        if not context_docs:
            logger.warning("No context documents supplied to synthesizer.")
            return None

        # Dynamically import templates to prevent circular dependencies
        try:
            from agents.concierge.prompt_templates import TEMPLATES
            template = TEMPLATES.get(domain, TEMPLATES.get("default"))
        except ImportError as e:
            logger.warning(f"Could not import prompt templates: {e}. Using a generic RAG prompt.")
            template = """Answer the user query based ONLY on the provided context.
If the answer cannot be found in the context, say that you do not know.

Context:
{context}

Query: {query}

Answer:"""

        # Format context
        formatted_context = ""
        for i, doc in enumerate(context_docs, 1):
            formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"

        prompt = template.format(context=formatted_context, query=query)

        if self.is_degraded:
            import time
            current_time = time.time()
            degraded_time = getattr(self, "degraded_at", 0)
            if current_time - degraded_time > 60.0:  # 60s cooldown
                self.is_degraded = False
                logger.info("GeminiSynthesizer synthesis cooldown expired. Attempting to restore service.")
            else:
                # Fallback to Ollama if Gemini is degraded
                if self.ollama_client:
                    try:
                        logger.info("Synthesizing response using local Ollama (qwen3:latest) (Gemini degraded)...")
                        response = self.ollama_client.invoke(prompt)
                        if response and response.content:
                            return response.content.strip()
                        else:
                            logger.warning("Ollama returned empty response.")
                    except Exception as e:
                        logger.error(f"Ollama generation failed: {e}")
                return None

        if self.client:
            import time
            max_retries = 3
            backoff = 2.0

            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                    )
                    if response.text:
                        self.is_degraded = False
                        return response.text.strip()
                    else:
                        logger.warning("Gemini model returned empty response text.")
                        break
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                        if "limit: 20" in str(e) or "day" in str(e).lower() or "daily" in str(e).lower():
                            self.is_degraded = True
                            self.degraded_at = time.time()
                            break
                        if attempt < max_retries - 1:
                            sleep_time = backoff ** (attempt + 1)
                            logger.warning(f"Gemini generation hit rate limit. Retrying in {sleep_time}s...")
                            time.sleep(sleep_time)
                            continue
                        else:
                            self.is_degraded = True
                            self.degraded_at = time.time()
                    logger.error(f"Gemini generation failed: {e}. Falling back to Ollama.")
                    break

        # Fallback to Ollama if client missing or Gemini failed
        if self.ollama_client:
            try:
                logger.info("Synthesizing response using local Ollama (qwen3:latest)...")
                response = self.ollama_client.invoke(prompt)
                if response and response.content:
                    return response.content.strip()
                else:
                    logger.warning("Ollama returned empty response.")
            except Exception as e:
                logger.error(f"Ollama generation failed: {e}")

        return None

    def check_sufficiency(self, query: str, context_docs: list, domain: str) -> str:
        """
        Determines whether the context contains sufficient information to answer the question.
        Returns 'SUFFICIENT', 'INSUFFICIENT', or None on failure/errors.
        """
        if not context_docs:
            return "INSUFFICIENT"
            
        formatted_context = ""
        for i, doc in enumerate(context_docs, 1):
            formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"
            
        prompt = f"""Question:
{query}

Context:
{formatted_context.strip()}

Determine whether the context contains information relevant to answering ANY PART of the question.

Reply only:

SUFFICIENT

or

INSUFFICIENT"""

        if self.is_degraded:
            import time
            current_time = time.time()
            degraded_time = getattr(self, "degraded_at", 0)
            if current_time - degraded_time > 60.0:  # 60s cooldown
                self.is_degraded = False
                logger.info("GeminiSynthesizer sufficiency check cooldown expired. Attempting to restore service.")
            else:
                # Fallback to Ollama if Gemini is degraded
                if self.ollama_client:
                    try:
                        logger.info("Checking sufficiency using local Ollama (qwen3:latest) (Gemini degraded)...")
                        response = self.ollama_client.invoke(prompt)
                        if response and response.content:
                            result = response.content.strip().upper()
                            if "SUFFICIENT" in result and "INSUFFICIENT" not in result:
                                return "SUFFICIENT"
                            return "INSUFFICIENT"
                        else:
                            logger.warning("Ollama relevance check returned empty response.")
                    except Exception as e:
                        logger.error(f"Ollama relevance check failed: {e}")
                return None

        if self.client:
            import time
            max_retries = 3
            backoff = 2.0

            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                    )
                    if response.text:
                        self.is_degraded = False
                        result = response.text.strip().upper()
                        if "SUFFICIENT" in result and "INSUFFICIENT" not in result:
                            return "SUFFICIENT"
                        return "INSUFFICIENT"
                    else:
                        logger.warning("Gemini relevance check returned empty response.")
                        break
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                        if "limit: 20" in str(e) or "day" in str(e).lower() or "daily" in str(e).lower():
                            self.is_degraded = True
                            self.degraded_at = time.time()
                            break
                        if attempt < max_retries - 1:
                            sleep_time = backoff ** (attempt + 1)
                            logger.warning(f"Gemini relevance check hit rate limit. Retrying in {sleep_time}s...")
                            time.sleep(sleep_time)
                            continue
                        else:
                            self.is_degraded = True
                            self.degraded_at = time.time()
                    logger.error(f"Gemini relevance check failed: {e}. Falling back to Ollama.")
                    break

        # Fallback to Ollama
        if self.ollama_client:
            try:
                logger.info("Checking sufficiency using local Ollama (qwen3:latest)...")
                response = self.ollama_client.invoke(prompt)
                if response and response.content:
                    result = response.content.strip().upper()
                    if "SUFFICIENT" in result and "INSUFFICIENT" not in result:
                        return "SUFFICIENT"
                    return "INSUFFICIENT"
                else:
                    logger.warning("Ollama relevance check returned empty response.")
            except Exception as e:
                logger.error(f"Ollama relevance check failed: {e}")

        return None
