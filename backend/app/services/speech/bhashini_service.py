"""
Bhashini Service — Speech-To-Text & Text-To-Speech wrapper for MeitY's Bhashini API.
Owner: Antigravity
"""

import base64
import logging
import os
import time
from typing import Any, Dict, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class BhashiniService:
    def __init__(self):
        self._cached_config = None
        self._last_fetched = 0
        self._cache_ttl = 3600  # 1 hour cache TTL for pipeline configs
        self.pipeline_url = (
            "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
        )
        self.inference_url = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"

    def has_credentials(self) -> bool:
        """Checks if Bhashini API credentials are set in configuration."""
        user_id = settings.BHASHINI_USER_ID
        api_key = settings.BHASHINI_API_KEY
        inf_key = settings.BHASHINI_INFERENCE_KEY

        return bool(
            user_id
            and user_id != "your_user_id"
            and api_key
            and api_key != "your_api_key"
            and inf_key
            and inf_key != "your_inference_key"
        )

    def _fetch_pipeline_config(self) -> Optional[Dict[str, Any]]:
        """
        Calls /getModelsPipeline to get the latest service IDs and callbacks.
        Caches the config in memory.
        """
        if not self.has_credentials():
            logger.warning("Bhashini credentials are not fully configured. Skipping config fetch.")
            return None

        # Check if cache is still valid
        if self._cached_config and (time.time() - self._last_fetched < self._cache_ttl):
            return self._cached_config

        logger.info("Fetching Bhashini pipeline configurations...")
        headers = {
            "userID": settings.BHASHINI_USER_ID,
            "ulcaApiKey": settings.BHASHINI_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "pipelineTasks": [
                {"taskType": "asr"},
                {"taskType": "translation"},
                {"taskType": "tts"},
            ],
            "pipelineRequestConfig": {"pipelineId": settings.BHASHINI_PIPELINE_ID},
        }

        try:
            # Short timeout to avoid blocking startup if MeitY services are slow
            resp = requests.post(self.pipeline_url, json=payload, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                self._cached_config = data
                self._last_fetched = time.time()
                logger.info("Successfully fetched Bhashini pipeline configurations.")

                # Check for dynamic callback URL in pipeline response
                callback_url = data.get("pipelineInferenceAPIEndPoint", {}).get("callbackUrl")
                if callback_url:
                    self.inference_url = callback_url
                    logger.info(f"Updated Bhashini inference endpoint to: {self.inference_url}")

                return data
            else:
                logger.error(
                    f"Bhashini pipeline configuration fetch failed: Status {resp.status_code} - {resp.text}"
                )
        except Exception as e:
            logger.error(f"Bhashini pipeline configuration query failed: {e}")

        # Return cached config as fallback if newer fetch failed
        return self._cached_config

    def _get_service_id(self, task_type: str, language: str) -> Optional[str]:
        """Dynamically finds the best service ID from cached configurations."""
        config = self._fetch_pipeline_config()
        if not config:
            # Static fallback IDs if MeitY config API is down
            fallbacks = {
                "asr": {
                    "hi": "ai4bharat/conformer-hi-gpu--t4",
                    "kn": "ai4bharat/conformer-multilingual-dravidian-gpu--t4",
                    "en": "ai4bharat/whisper-medium-en-gpu--t4",
                },
                "tts": {
                    "hi": "ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4",
                    "kn": "ai4bharat/indic-tts-coqui-dravidian-gpu--t4",
                    "en": "ai4bharat/indic-tts-coqui-misc-gpu--t4",
                },
            }
            sid = fallbacks.get(task_type, {}).get(language)
            logger.info(
                f"Using hardcoded static fallback service ID for {task_type} ({language}): {sid}"
            )
            return sid

        try:
            tasks = config.get("pipelineResponseConfig", [])
            for task in tasks:
                if task.get("taskType") == task_type:
                    config_list = task.get("config", [])
                    # Match by source language
                    for cfg in config_list:
                        lang_cfg = cfg.get("language", {})
                        if lang_cfg.get("sourceLanguage") == language:
                            return cfg.get("serviceId")
        except Exception as e:
            logger.error(f"Error parsing Bhashini serviceId from config: {e}")

        return None

    def transcribe_audio(self, audio_base64: str, language: str = "hi") -> Optional[str]:
        """
        Transcribes base64 encoded audio using Bhashini ASR pipeline.
        Returns transcribed text or None on failure.
        """
        if not self.has_credentials():
            return None

        # Fetch configurations (or fallback) to get the correct service ID
        service_id = self._get_service_id("asr", language)
        if not service_id:
            logger.error(f"No Bhashini ASR service ID found for language: {language}")
            return None

        logger.info(f"Sending ASR request to Bhashini (lang={language}, serviceId={service_id})...")

        headers = {
            "Authorization": settings.BHASHINI_INFERENCE_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": language},
                        "serviceId": service_id,
                        "audioFormat": "wav",
                        "samplingRate": 16000,
                    },
                }
            ],
            "inputData": {"audio": [{"audioContent": audio_base64}]},
        }

        try:
            resp = requests.post(self.inference_url, json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                resp_json = resp.json()
                outputs = resp_json.get("pipelineResponse", [{}])[0].get("output", [{}])
                transcript = outputs[0].get("source") or outputs[0].get("target") or ""
                logger.info(f"Bhashini ASR success: '{transcript}'")
                return transcript.strip()
            else:
                logger.error(
                    f"Bhashini ASR inference failed: Status {resp.status_code} - {resp.text}"
                )
        except Exception as e:
            logger.error(f"Bhashini ASR call exception: {e}")

        return None

    def synthesize_speech(self, text: str, language: str, filepath: str) -> bool:
        """
        Synthesizes text to speech using Bhashini TTS pipeline and saves to file.
        Returns True on success, False on failure.
        """
        if not self.has_credentials():
            return False

        # Get service ID
        service_id = self._get_service_id("tts", language)
        if not service_id:
            logger.error(f"No Bhashini TTS service ID found for language: {language}")
            return False

        logger.info(f"Sending TTS request to Bhashini (lang={language}, serviceId={service_id})...")

        headers = {
            "Authorization": settings.BHASHINI_INFERENCE_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": language},
                        "serviceId": service_id,
                        "gender": "female",
                    },
                }
            ],
            "inputData": {"input": [{"source": text}]},
        }

        try:
            resp = requests.post(self.inference_url, json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                resp_json = resp.json()
                audio_objs = resp_json.get("pipelineResponse", [{}])[0].get("audio", [{}])
                audio_base64 = audio_objs[0].get("audioContent")

                if audio_base64:
                    audio_bytes = base64.b64decode(audio_base64)

                    # Ensure parent directory exists
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)

                    with open(filepath, "wb") as f:
                        f.write(audio_bytes)
                    logger.info(f"Bhashini TTS success: saved audio file to {filepath}")
                    return True
                else:
                    logger.error("Bhashini TTS response did not contain audioContent.")
            else:
                logger.error(
                    f"Bhashini TTS inference failed: Status {resp.status_code} - {resp.text}"
                )
        except Exception as e:
            logger.error(f"Bhashini TTS call exception: {e}")

        return False


# Singleton instance
bhashini_service = BhashiniService()
