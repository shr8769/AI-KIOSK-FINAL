import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class BaseTranslator(ABC):
    """
    Abstract Base Class for translation components.
    Ensures pluggability so that Gemini translation can easily be replaced
    with local neural machine translation pipelines like IndicTrans2.
    """
    @abstractmethod
    def translate_to_english(self, text: str) -> Tuple[str, str]:
        """
        Detects query language and translates it to English.
        Returns:
            Tuple[str, str]: (translated_text, detected_language) where language code is 'en', 'kn', or 'hi'.
        """
        pass

    @abstractmethod
    def translate_from_english(self, text: str, target_lang: str) -> str:
        """
        Translates text from English to target language.
        """
        pass


class GeminiTranslator(BaseTranslator):
    """
    Translator implementation using Google's Gemini models via the google-genai SDK.
    Used for initial prototype before offline IndicTrans2 deployment.
    """
    def __init__(self, api_key: str = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client for translation: {e}")
        else:
            logger.warning("GEMINI_API_KEY not found. Translator running in passthrough mode.")

    def translate_to_english(self, text: str) -> Tuple[str, str]:
        if not self.client:
            return text, "en"

        prompt = f"""You are a multilingual translation assistant.
Analyze the following text query from a university kiosk user:
"{text}"

1. Classify the language of the query as exactly one of: 'kn' (Kannada), 'hi' (Hindi), or 'en' (English).
2. If it is Kannada ('kn') or Hindi ('hi'), translate it to English.
3. If it is English ('en'), return the query unmodified.

Return your response strictly in the following JSON format, with no markdown styling:
{{
  "detected_language": "en" | "kn" | "hi",
  "translated_text": "the translated English query"
}}
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            result = json.loads(response.text.strip())
            detected = result.get("detected_language", "en")
            translated = result.get("translated_text", text)
            
            if detected == "en":
                return text, "en"
                
            logger.info(f"Translated user query from '{detected}' to English: '{text}' -> '{translated}'")
            return translated, detected
        except Exception as e:
            logger.error(f"Gemini translation to English failed: {e}. Falling back to passthrough.")
            return text, "en"

    def translate_from_english(self, text: str, target_lang: str) -> str:
        if not self.client or target_lang == "en" or not text:
            return text

        prompt = f"""You are a professional university kiosk translation assistant.
Translate the following English text into the target language: '{target_lang}' ('kn' for Kannada, 'hi' for Hindi).
Provide a natural, conversational translation that captures the exact meaning of the original context.

English Text:
{text}

Translation:"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.text:
                return response.text.strip()
            return text
        except Exception as e:
            logger.error(f"Gemini translation from English to '{target_lang}' failed: {e}. Returning original text.")
            return text


class IndicTrans2Translator(BaseTranslator):
    """
    Future implementation placeholder using AI4Bharat's IndicTrans2 for offline/local translation.
    
    Architecture for replacement:
    1. Install `torch`, `transformers` and set up GPU context.
    2. Download IndicTrans2 model checkpoints (e.g. `indictrans2-en-indic` and `indictrans2-indic-en`).
    3. Load tokenizer and model weights locally.
    4. Override methods below to execute local model forward passes.
    """
    def __init__(self, model_dir: str = None):
        self.model_dir = model_dir
        # TODO: Initialize IndicTrans2 pipeline loaders here
        pass

    def translate_to_english(self, text: str) -> Tuple[str, str]:
        # TODO: Run LID model to detect language (kn/hi/en), then run indic-en translation
        logger.info("IndicTrans2 translate_to_english placeholder called.")
        return text, "en"

    def translate_from_english(self, text: str, target_lang: str) -> str:
        # TODO: Run en-indic translation to target_lang
        logger.info("IndicTrans2 translate_from_english placeholder called.")
        return text
