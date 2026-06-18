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
    """
    def __init__(self, api_key: str = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None
        self.is_degraded = False
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Gemini client successfully with model {model_name}.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}. RAG synthesis will fallback to retrieval-only.")
        else:
            logger.warning("GEMINI_API_KEY not found in environment. Running in retrieval-only fallback mode.")

    def synthesize(self, query: str, context_docs: list, domain: str) -> str:
        """
        Synthesizes an answer using the query and a list of context documents based on the domain prompt template.
        If Gemini is unavailable or errors out, returns None to signal fallback to retrieval-only mode.
        """
        if self.is_degraded:
            return None

        if not context_docs:
            logger.warning("No context documents supplied to synthesizer.")
            return None

        if not self.client:
            logger.warning("Gemini client is not initialized. RAG synthesis unavailable.")
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

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.text:
                return response.text.strip()
            else:
                logger.warning("Gemini model returned empty response text.")
                return None
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}. Falling back to retrieval-only mode.")
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                self.is_degraded = True
            return None

    def check_sufficiency(self, query: str, context_docs: list, domain: str) -> str:
        """
        Determines whether the context contains sufficient information to answer the question.
        Returns 'SUFFICIENT', 'INSUFFICIENT', or None on failure/errors.
        """
        if self.is_degraded:
            return None

        if not context_docs:
            return "INSUFFICIENT"
            
        if not self.client:
            logger.warning("Gemini client is not initialized. Sufficiency check bypassed.")
            return None
            
        formatted_context = ""
        for i, doc in enumerate(context_docs, 1):
            formatted_context += f"Document {i} (ID: {doc.get('id', 'unknown')}):\n{doc.get('document', '')}\n\n"
            
        prompt = f"""Question:
{query}

Context:
{formatted_context.strip()}

Determine whether the context contains sufficient information to answer the question.

Reply only:

SUFFICIENT

or

INSUFFICIENT"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.text:
                result = response.text.strip().upper()
                if "SUFFICIENT" in result and "INSUFFICIENT" not in result:
                    return "SUFFICIENT"
                return "INSUFFICIENT"
            else:
                logger.warning("Gemini relevance check returned empty response.")
                return None
        except Exception as e:
            logger.error(f"Gemini relevance check failed: {e}")
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                self.is_degraded = True
            return None
