"""Ollama-compatible LLM client.

Targets either:
- A local Ollama daemon at http://localhost:11434 (no auth).
- Ollama Cloud at https://ollama.com (Bearer auth via OLLAMA_API_KEY).

Selected by setting LLM_PROVIDER=ollama (or ollama_cloud) in the environment.
The legacy LiquidClient in core/llm/client.py remains available when
LLM_PROVIDER is unset or set to a value other than ollama*.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from threading import Lock
from typing import Any, Optional


class OllamaClient:
    _instance: Optional["OllamaClient"] = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self) -> None:
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", "")
        self.api_key = os.environ.get("OLLAMA_API_KEY", "")
        self.timeout = int(os.environ.get("OLLAMA_TIMEOUT", "180"))

        if not self.model:
            raise RuntimeError(
                "OLLAMA_MODEL is not set. Add it to .env (see the file for common cloud model IDs)."
            )

        provider_label = "Ollama Cloud" if "ollama.com" in self.base_url else "local Ollama"
        print(f"Initializing {provider_label} client (model={self.model}, base={self.base_url}).")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def generate(self, prompt: str, max_new_tokens: int = 1024, do_sample: bool = False) -> str:
        """Non-streaming completion via /api/generate. Returns the raw text.

        ``think: False`` is always sent so reasoning models (kimi-k2.6,
        deepseek-r1, gpt-oss thinking variants) place their full answer in
        ``response`` instead of consuming the token budget on chain-of-thought
        emitted into a separate ``thinking`` field. The MCP pipeline parses
        ``response`` only.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "num_predict": max_new_tokens,
                "temperature": 0.0 if not do_sample else 0.7,
            },
        }
        attempts = 0
        while True:
            try:
                result = self._post("/api/generate", payload)
                return result.get("response", "") or ""
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8")[:300]
                except Exception:
                    pass
                if exc.code in (429, 500, 502, 503, 504) and attempts < 3:
                    attempts += 1
                    time.sleep(2 ** attempts)
                    continue
                print(f"Ollama HTTPError {exc.code}: {body}")
                return ""
            except Exception as exc:
                if attempts < 2:
                    attempts += 1
                    time.sleep(1 + attempts)
                    continue
                print(f"Ollama request failed: {exc}")
                return ""


__all__ = ["OllamaClient"]
