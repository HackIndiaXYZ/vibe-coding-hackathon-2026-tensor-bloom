"""Per-role / per-tool LLM router (ARCHITECTURE §5.7).

Single entrypoint for every LLM call in the worker. Nodes call
`router.acall(role="implementer", messages=...)` — never litellm directly. The
router resolves the role/tool to a (provider, model, api_key_env) triple from
config/llm-routing.yaml, tries the primary then the fallback chain, records cost
to the `messages` table, and tracks provider health in Redis.

A `provider: none` entry is valid (deterministic local tools — no LLM call).
A `provider: mock` entry returns a synthetic response so the graph can run with
no API keys (fast dev inner loop, per ROADMAP Day 3).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@dataclass
class LLMResult:
    content: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    from_cache: bool = False


class ProviderNoneError(ValueError):
    """Raised when a role/tool is configured as provider: none."""


# Provider -> the env var holding the operator's key (used when a user picks a
# provider but supplies no BYO key of their own).
_DEFAULT_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class LLMRouter:
    def __init__(self, routing_config: dict, *, pool=None, redis=None) -> None:
        self.cfg = routing_config or {}
        self._pool = pool
        self._redis = redis

    # ── resolution ───────────────────────────────────────────────────────────
    def _override_spec(self, ov: dict) -> dict:
        return {
            "provider": ov["provider"],
            "model": ov["model"],
            "api_key_env": _DEFAULT_KEY_ENV.get(ov["provider"], ""),
        }

    def _operator_spec(self, role: str | None, tool: str | None) -> dict:
        tools = self.cfg.get("tools", {})
        roles = self.cfg.get("roles", {})
        if tool and tool in tools and tools[tool]:
            return tools[tool]
        if role and role in roles and roles[role]:
            return roles[role]
        return self.cfg.get("defaults", {})

    def _resolve(self, role: str | None, tool: str | None, overrides: dict | None = None) -> dict:
        """Precedence: explicit user override[tool|role] > deterministic 'none' >
        user "_default" (use-for-all-roles) > operator config."""
        if overrides:
            for key in (tool, role):
                ov = overrides.get(key) if key else None
                if ov and ov.get("provider") and ov.get("model"):
                    return self._override_spec(ov)

        op = self._operator_spec(role, tool)
        # deterministic tools (repo_map/lint/test_runner) never get an LLM
        if op.get("provider") == "none":
            return op
        # the user's single "default for all roles" applies to anything not set
        if overrides:
            d = overrides.get("_default")
            if d and d.get("provider") and d.get("model"):
                return self._override_spec(d)
        return op

    def is_none(self, role: str | None = None, tool: str | None = None) -> bool:
        return self._resolve(role, tool).get("provider") == "none"

    def effective_provider(self, role: str | None = None, tool: str | None = None,
                           overrides: dict | None = None) -> str:
        """The provider/model that WOULD be used — for surfacing mock vs real."""
        spec = self._resolve(role, tool, overrides)
        return spec.get("provider", "")

    def effective_model(self, role: str | None = None, tool: str | None = None,
                        overrides: dict | None = None) -> str:
        return self._resolve(role, tool, overrides).get("model", "")

    # ── main call ────────────────────────────────────────────────────────────
    async def acall(
        self,
        *,
        role: str | None = None,
        tool: str | None = None,
        messages: list[dict],
        task_id: int | None = None,
        temperature: float | None = None,
        max_tokens: int = 2048,
        overrides: dict | None = None,
        key_overrides: dict | None = None,
        **kw: Any,
    ) -> LLMResult:
        spec = self._resolve(role, tool, overrides)
        if spec.get("provider") == "none":
            raise ProviderNoneError(f"role={role} tool={tool} configured as 'none'")

        # L1 exact-hash cache (the one Redis cache layer shipped in MVP).
        cache_key = self._exact_key(spec, messages, temperature)
        if self._redis is not None and cache_key:
            cached = await self._cache_get(cache_key)
            if cached is not None:
                if task_id is not None:
                    await self._record(task_id, role, tool, cached)
                return cached

        chain = [spec, *spec.get("fallback", [])]
        # Safety net: a user override has no fallback of its own, so if it errors
        # (rate limit, bad key, provider down) fall back to the operator config for
        # this role — and ultimately to its fallbacks — instead of failing the goal.
        if overrides:
            op = self._resolve(role, tool)  # operator config, ignoring overrides
            if op.get("provider") not in (None, "none"):
                chain += [op, *op.get("fallback", [])]

        last_err: Exception | None = None
        for s in chain:
            provider = s.get("provider")
            try:
                if provider == "mock":
                    result = self._mock(s, messages)
                else:
                    result = await self._litellm(s, messages, temperature, max_tokens, key_overrides, **kw)
            except Exception as e:  # noqa: BLE001 — try next provider
                last_err = e
                log.warning("llm provider failed", provider=provider, err=str(e))
                await self._mark_health(provider, failed=True)
                continue

            if self._redis is not None and cache_key:
                await self._cache_put(cache_key, result)
            if task_id is not None:
                await self._record(task_id, role, tool, result)
            return result

        raise last_err or RuntimeError("no provider in chain")

    # ── provider backends ────────────────────────────────────────────────────
    async def _litellm(
        self, spec: dict, messages: list[dict], temperature: float | None,
        max_tokens: int, key_overrides: dict | None = None, **kw: Any,
    ) -> LLMResult:
        from litellm import acompletion

        provider = spec["provider"]
        model = spec["model"]
        # BYO user key wins; else operator env key.
        api_key = (key_overrides or {}).get(provider) or os.environ.get(spec.get("api_key_env", ""), "")
        resp = await acompletion(
            model=f"{provider}/{model}",
            api_key=api_key or None,
            messages=messages,
            temperature=spec.get("temperature", temperature if temperature is not None else 0.2),
            max_tokens=max_tokens,
            num_retries=2,  # litellm backs off on transient 429/5xx before we fall through
            **kw,
        )
        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        tin = int(getattr(usage, "prompt_tokens", 0) or 0)
        tout = int(getattr(usage, "completion_tokens", 0) or 0)
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
        cost = 0.0
        try:
            from litellm import completion_cost

            cost = float(completion_cost(completion_response=resp) or 0.0)
        except Exception:  # noqa: BLE001 — cost is best-effort
            cost = 0.0
        return LLMResult(
            content=choice.message.content or "",
            model=model,
            provider=provider,
            tokens_in=tin,
            tokens_out=tout,
            cached_tokens=cached,
            cost_usd=cost,
        )

    def _mock(self, spec: dict, messages: list[dict]) -> LLMResult:
        # Deterministic synthetic response: echo a short canned payload so graph
        # nodes that expect JSON can still parse. Cost is a nominal fixed value.
        last = messages[-1]["content"] if messages else ""
        tin = sum(len(str(m.get("content", ""))) for m in messages) // 4
        content = spec.get("mock_response", '{"ok": true, "mock": true}')
        log.debug("mock llm call", model=spec.get("model"), prompt_chars=len(str(last)))
        return LLMResult(
            content=content,
            model=spec.get("model", "mock"),
            provider="mock",
            tokens_in=tin,
            tokens_out=len(content) // 4,
            cached_tokens=0,
            cost_usd=float(spec.get("mock_cost_usd", 0.0001)),
        )

    # ── cost recording ───────────────────────────────────────────────────────
    async def _record(self, task_id: int, role: str | None, tool: str | None, r: LLMResult) -> None:
        if self._pool is None:
            return
        await self._pool.execute(
            """
            INSERT INTO messages
                (task_id, role, content, tool_name, tokens_in, tokens_out, cached_tokens, cost_usd)
            VALUES ($1, 'assistant', $2, $3, $4, $5, $6, $7)
            """,
            task_id, r.content, tool, r.tokens_in, r.tokens_out, r.cached_tokens, r.cost_usd,
        )

    # ── exact cache ──────────────────────────────────────────────────────────
    def _exact_key(self, spec: dict, messages: list[dict], temperature: float | None) -> str | None:
        if spec.get("provider") in (None, "none"):
            return None
        bucket = "low" if (temperature or 0) <= 0.3 else "medium" if (temperature or 0) <= 0.7 else "high"
        raw = json.dumps(
            {"m": f"{spec.get('provider')}/{spec.get('model')}", "msgs": messages, "t": bucket},
            sort_keys=True, default=str,
        )
        return "llm:exact:" + hashlib.sha256(raw.encode()).hexdigest()

    async def _cache_get(self, key: str) -> LLMResult | None:
        try:
            blob = await self._redis.get(key)
        except Exception:  # noqa: BLE001
            return None
        if not blob:
            return None
        d = json.loads(blob)
        return LLMResult(
            content=d["content"], model=d["model"], provider=d["provider"],
            tokens_in=d.get("tokens_in", 0), tokens_out=d.get("tokens_out", 0),
            cached_tokens=d.get("cached_tokens", 0), cost_usd=0.0, from_cache=True,
        )

    async def _cache_put(self, key: str, r: LLMResult) -> None:
        try:
            await self._redis.set(
                key,
                json.dumps({
                    "content": r.content, "model": r.model, "provider": r.provider,
                    "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                    "cached_tokens": r.cached_tokens,
                }),
                ex=24 * 3600,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _mark_health(self, provider: str | None, *, failed: bool) -> None:
        if self._redis is None or not provider:
            return
        try:
            await self._redis.incr(f"llm:provider:{provider}:{'errors' if failed else 'ok'}")
        except Exception:  # noqa: BLE001
            pass


def load_routing_config(path: str) -> dict:
    import yaml

    with open(path) as f:
        return yaml.safe_load(f) or {}
