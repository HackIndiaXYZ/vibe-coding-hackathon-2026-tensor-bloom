"""diff_analysis — per-file classification + dangerous-pattern detection.

Rules-based for MVP (no LLM call). Drives the dangerous-action gate
(ARCHITECTURE §9.5): CI-config edits, mass deletions, secret-shaped strings.
"""

from __future__ import annotations

import re

from .base import BaseTool

_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "github_token"),
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"), "anthropic_key"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "openai_key"),
    (re.compile(r"sk_live_[A-Za-z0-9]{20,}"), "stripe_key"),
]


def _classify(path: str) -> str:
    p = path.lower()
    if "test" in p or "/tests/" in p or p.endswith("_test.go"):
        return "test"
    if p.endswith((".md", ".rst", ".txt")) or "/docs/" in p:
        return "docs"
    if ".github/workflows" in p or p.endswith((".yml", ".yaml", ".toml", ".ini", ".cfg")):
        return "config"
    return "code"


def _is_ci(path: str) -> bool:
    p = path.lower()
    return ".github/workflows" in p or (path.count("/") == 0 and p.endswith((".yml", ".yaml")))


def analyze_diff(diff: str) -> dict:
    """Pure function: classify hunks + flag dangerous patterns. Unit-testable."""
    files: list[dict] = []
    dangerous: list[str] = []
    cur: dict | None = None

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            if cur:
                files.append(cur)
            # path from "diff --git a/<path> b/<path>"
            m = re.search(r" b/(.+)$", line)
            path = m.group(1) if m else "?"
            cur = {"path": path, "added": 0, "removed": 0, "category": _classify(path)}
        elif cur is not None:
            if line.startswith("+") and not line.startswith("+++"):
                cur["added"] += 1
                for pat, label in _SECRET_PATTERNS:
                    if pat.search(line):
                        dangerous.append(f"possible {label} in {cur['path']}")
            elif line.startswith("-") and not line.startswith("---"):
                cur["removed"] += 1
    if cur:
        files.append(cur)

    for f in files:
        if _is_ci(f["path"]):
            dangerous.append(f"CI config modified: {f['path']}")
        total = f["added"] + f["removed"]
        if total >= 20 and f["removed"] >= 0.5 * total and f["removed"] > f["added"]:
            dangerous.append(f"mass deletion in {f['path']} (-{f['removed']}/+{f['added']})")

    return {
        "files": files,
        "dangerous": bool(dangerous),
        "dangerous_reasons": sorted(set(dangerous)),
    }


class DiffAnalysisTool(BaseTool):
    name = "diff_analysis"
    cacheable = False

    async def run(self, diff: str) -> dict:
        await self._guard()
        return analyze_diff(diff)
