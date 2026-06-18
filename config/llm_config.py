# llm_config.py
# Configuration settings for Qwen and Gemini LLMs.

import os
from dotenv import load_dotenv

load_dotenv()

# Ollama details
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

# Gemini details
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Primary LLM choice: 'qwen' or 'gemini'
PRIMARY_LLM = os.getenv("PRIMARY_LLM", "qwen")
