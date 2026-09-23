"""
audit_engine/config.py

Model-agnostic by design: every LLM call in the project goes through
get_model(). Change the KORVAI_MODEL env var, every node switches models -
no hardcoded model string anywhere else in the codebase.
"""

import os
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv
load_dotenv()

DEFAULT_MODEL = "ollama:llama3.1:8b"


def get_model():
    return init_chat_model(os.environ.get("KORVAI_MODEL", DEFAULT_MODEL))