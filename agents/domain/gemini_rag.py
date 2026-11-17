import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    backend_env = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)

logger = logging.getLogger(__name__)

class GeminiSynthesizer:
    """
    A wrapper class to interface with Google's Gemini models for synthesizing
    retrieved context documents into natural language answers (RAG).
    Provides compatibility fallbacks if Google GenAI SDK or API keys are missing.
    Fallback to local Qwen (Ollama) is used if GEMINI_API_KEY is not set.
    """
    def __init__(self, api_key: str = None, model_name: str = "gemini-3.8-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None
        self.ollama_client = None
        self.is_degraded = False
        self.degraded_at = 0.0
        
        if self.api_key:
            try:
                primary_key = self.api_key.split(",")[0].strip().strip('"').strip("'")
                from google import genai
                self.client = genai.Client(api_key=primary_key)
                logger.info(f"Initialized Gemini client successfully with model {model_name}.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}. Falling back exclusively to local Ollama.")
        else:
            logger.info("GEMINI_API_KEY not found in environment. Relying exclusively on local Ollama.")
            
        # ALWAYS initialize Ollama so it's ready as a fallback if Gemini goes down
        self._init_ollama()

    def _init_ollama(self):
        try:
            from langchain_ollama import ChatOllama
            self.ollama_client = ChatOllama(model="qwen3:latest")
            logger.info("Initialized local Ollama client (qwen3:latest) for fallback.")
        except ImportError as e:
            logger.warning(f"langchain_ollama not installed. Fallback unavailable. {e}")
            self.ollama_client = None

    def synthesize(self, query: str, context_docs: list, domain: str) -> str:
        """
        Synthesizes an answer using the query and a list of context documents based on the domain prompt template.
        If Gemini is unavailable or errors out, falls back to local Ollama (Qwen) synthesis.
        If both are unavailable, returns None.
        """
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
        if context_docs:
            for i, doc in enumerate(context_docs, 1):
                formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"
        
        # Some templates don't require {context} (e.g., conversational rewrites).
        # We try to format with context, and if that fails or isn't needed, we just use the query.
        try:
            if "{context}" in template:
                prompt = template.format(context=formatted_context, query=query)
            else:
                prompt = template.format(query=query)
        except Exception:
            prompt = query

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

        from config.gemini_pool import gemini_pool
        client, active_key = gemini_pool.get_active_client()
        if client:
            models_to_try = gemini_pool.get_models()
            for m in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config={
                            'temperature': 0.3,
                            'automatic_function_calling': {'disable': True}
                        }
                    )
                    if response and response.text:
                        self.is_degraded = False
                        return response.text.strip()
                    else:
                        logger.warning(f"Gemini model {m} returned empty response text.")
                except Exception as e:
                    err_msg = str(e)
                    if any(term in err_msg for term in ["504", "DEADLINE_EXCEEDED", "Gateway Timeout", "503", "UNAVAILABLE", "high demand", "timed out", "Timeout"]):
                        logger.warning(f"Gemini server error / timeout on key ending in ...{active_key[-6:]}: {e}")
                        gemini_pool.mark_exhausted(active_key, retry_delay_seconds=120.0)
                        next_client, next_key = gemini_pool.get_active_client()
                        if next_client and next_key != active_key:
                            logger.info(f"Rotating to standby Gemini key ending in ...{next_key[-6:]}")
                            client = next_client
                            active_key = next_key
                            continue
                        else:
                            gemini_pool.mark_degraded(60.0)
                            self.is_degraded = True
                            self.degraded_at = time.time()
                            break
                    elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        logger.warning(f"Gemini quota exhausted on key ending in ...{active_key[-6:]}: {e}")
                        gemini_pool.mark_exhausted(active_key)
                        next_client, next_key = gemini_pool.get_active_client()
                        if next_client and next_key != active_key:
                            client = next_client
                            active_key = next_key
                            continue
                        else:
                            self.is_degraded = True
                            self.degraded_at = time.time()
                            break
                    logger.warning(f"Gemini generation with {m} failed: {e}. Falling back to Ollama.")
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

Determine whether the context contains any relevant information that can help address or partially answer the query. If there is any useful or partially matching information in the context, reply with SUFFICIENT. Only reply with INSUFFICIENT if the context is completely unrelated or contains absolutely no helpful facts.

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
                        config={
                            'automatic_function_calling': {'disable': True}
                        }
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
