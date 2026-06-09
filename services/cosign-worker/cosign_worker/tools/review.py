"""review — compose/normalize the reviewer's output into the fixed ReviewDraft
schema the UI can render and edit (ARCHITECTURE §6.5). No LLM; pure shaping.

The reviewer node calls the LLM (via router) to produce raw review content, then
passes it here to coerce into the schema the web ReviewEditor expects.
"""

from __future__ import annotations

import json

from .base import BaseTool


def compose_review(raw: dict | str) -> dict:
    """Coerce arbitrary reviewer output into the ReviewDraft schema.

    Tolerant of missing keys / a JSON string. Always returns the full shape so
    the UI never sees an undefined field.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {"summary": raw}
    if not isinstance(raw, dict):
        raw = {}

    def _str_list(v) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        if v:
            return [str(v)]
        return []

    per_file = []
    for c in raw.get("per_file_comments", []) or []:
        if isinstance(c, dict):
            per_file.append({
                "path": str(c.get("path", "")),
                "line": int(c.get("line", 0) or 0),
                "comment": str(c.get("comment", "")),
            })

    risk = raw.get("risk_score", 0.0)
    try:
        risk = float(risk)
    except (TypeError, ValueError):
        risk = 0.0

    return {
        "summary": str(raw.get("summary", "")),
        "risk_score": max(0.0, min(1.0, risk)),
        "per_file_comments": per_file,
        "ask_changes": _str_list(raw.get("ask_changes")),
        "praise": _str_list(raw.get("praise")),
    }


def review_to_markdown(draft: dict) -> str:
    """Render a ReviewDraft as the markdown body posted to the PR (as the user)."""
    lines = [draft.get("summary", "").strip(), ""]
    asks = draft.get("ask_changes") or []
    if asks:
        lines.append("**Requested changes**")
        lines += [f"- {a}" for a in asks]
        lines.append("")
    praise = draft.get("praise") or []
    if praise:
        lines.append("**Praise**")
        lines += [f"- {p}" for p in praise]
        lines.append("")
    pfc = draft.get("per_file_comments") or []
    if pfc:
        lines.append("**Per-file notes**")
        for c in pfc:
            loc = f"{c['path']}:{c['line']}" if c.get("line") else c["path"]
            lines.append(f"- `{loc}` — {c['comment']}")
    return "\n".join(lines).strip() + "\n"


class ReviewTool(BaseTool):
    name = "review"
    cacheable = False

    async def run(self, raw: dict | str) -> dict:
        await self._guard()
        return compose_review(raw)
