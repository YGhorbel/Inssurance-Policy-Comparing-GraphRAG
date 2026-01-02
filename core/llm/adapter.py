"""Simple adapter to unify LLM interfaces used across the project.

Provides `get_llm()` which returns an object exposing `generate(prompt, **kwargs)`.
It prefers Ollama (if langchain_community.llms.Ollama is installed) and falls
back to the project's `core.llm.client.get_llm_client()` otherwise.
"""
from typing import Any

try:
    from langchain_community.llms import Ollama
except Exception:
    Ollama = None

try:
    from core.llm.client import get_llm_client
except Exception:
    get_llm_client = None


class OllamaAdapter:
    def __init__(self, model: str = "llama3:8b", temperature: float = 0.3):
        self.client = Ollama(model=model, temperature=temperature)

    def generate(self, prompt: str, **kwargs) -> str:
        # Ollama client exposes different method names depending on version
        if hasattr(self.client, "invoke"):
            return self.client.invoke(prompt)
        if hasattr(self.client, "generate"):
            return self.client.generate(prompt)
        # Fallback to calling as a callable
        try:
            return self.client(prompt)
        except Exception:
            return ""


class FallbackAdapter:
    def __init__(self):
        self.client = get_llm_client() if get_llm_client is not None else None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.client:
            return "Error: No LLM available"
        # LiquidClient provides generate(prompt)
        if hasattr(self.client, "generate"):
            return self.client.generate(prompt)
        # Other client surfaces
        if hasattr(self.client, "invoke"):
            return self.client.invoke(prompt)
        try:
            return self.client(prompt)
        except Exception:
            return ""


def get_llm():
    """Return an object with a `generate(prompt)` method.

    Preference order:
    1. Ollama (if installed)
    2. Fallback to `core.llm.client.get_llm_client()`
    """
    if Ollama is not None:
        try:
            return OllamaAdapter()
        except Exception:
            pass

    return FallbackAdapter()


__all__ = ["get_llm", "OllamaAdapter", "FallbackAdapter"]
