"""Shared node helpers: prompt building + tolerant JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from ...llm.prompt_cache import system_message

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def build_messages(system_text: str, user_text: str) -> list[dict]:
    """System block carries the cache breakpoint (static-first); user is dynamic."""
    return [system_message(system_text), {"role": "user", "content": user_text}]


def parse_json(content: str, default: Any = None) -> Any:
    """Parse a JSON object out of LLM content; tolerant of prose around it."""
    if not content:
        return default if default is not None else {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    m = _JSON_RE.search(content)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return default if default is not None else {}
