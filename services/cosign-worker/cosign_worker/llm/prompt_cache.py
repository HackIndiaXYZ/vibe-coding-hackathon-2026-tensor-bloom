"""Anthropic prompt-cache helper (ARCHITECTURE §5.1).

Marks the static prefix (system prompt + tool defs + repo context) with
cache_control so it is served at 0.1x on repeat. STRICT rule: everything static
goes in the cached system block; dynamic content (the diff, the user ask) goes
in the messages list AFTER the breakpoint. Any change before the breakpoint
busts the whole cache.
"""

from __future__ import annotations


def cached_system(text: str) -> list[dict]:
    """Build an Anthropic-style system block with an ephemeral cache breakpoint.

    litellm passes this through to Anthropic's `cache_control`. For non-Anthropic
    providers litellm ignores the marker and the stable prefix still benefits
    from OpenAI's automatic prefix cache.
    """
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def system_message(text: str) -> dict:
    """A system message whose content carries the cache breakpoint."""
    return {"role": "system", "content": cached_system(text)}
