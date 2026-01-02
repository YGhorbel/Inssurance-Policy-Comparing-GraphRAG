from typing import Any, Dict


class Context:
    """Lightweight context store for agents.

    Intended for short-lived, in-memory storage of values that agents
    may want to persist across steps (e.g. last query, top chunk).
    """

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._store)


__all__ = ["Context"]
