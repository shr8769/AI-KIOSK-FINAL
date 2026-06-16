import os
import logging

logger = logging.getLogger(__name__)

class GeminiSynthesizer:
    """
    A wrapper class to interface with Google's Gemini models for synthesizing
    retrieved context documents into natural language answers (RAG).
    Provides compatibility fallbacks if Google GenAI SDK or API keys are missing.
    """
    def __init__(self, api_key: str = None, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None
        
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerationalModel(model_name)
                logger.info(f"Initialized Gemini model {model_name} successfully.")
            except ImportError:
                logger.warning("google-generativeai SDK is not installed. Will fallback to mock RAG answers.")
        else:
            logger.warning("GEMINI_API_KEY not found in environment. Running in fallback/mock RAG mode.")

    def synthesize(self, query: str, context_docs: list) -> str:
        """
        Synthesizes an answer using the query and a list of context documents.
        """
        if not context_docs:
            return "No context documents were found to construct an answer."

        # Format context
        formatted_context = ""
        for i, doc in enumerate(context_docs, 1):
            formatted_context += f"Document {i} (Source: {doc.get('metadata', {}).get('category', 'unknown')}):\n{doc.get('document', '')}\n\n"

        prompt = f"""You are a helpful and knowledgeable university AI assistant.
Your task is to answer the student's query based ONLY on the provided context documents.
If the context documents do not contain the answer, politely state that you do not know.
Keep the answer clear, natural, and concise.

Student Query: {query}

Context Documents:
{formatted_context}

Answer:"""

        if self.client:
            try:
                response = self.client.generate_content(prompt)
                return response.text.strip()
            except Exception as e:
                logger.error(f"Gemini API generation failed: {e}. Falling back to default RAG response.")
                
        # Mock RAG fallback (combining top retrieved document answers with a note)
        best_doc = context_docs[0]
        category = best_doc.get("metadata", {}).get("category", "general").title().replace('_', ' ')
        answer_part = best_doc.get("answer", best_doc.get("document", ""))
        
        return f"[Synthesized RAG Response (Mock Mode)] Based on {category} data:\n{answer_part}"
