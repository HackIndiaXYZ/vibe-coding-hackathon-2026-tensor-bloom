"""lint — detect the repo's linter, run it in the sandbox, return violations.

No LLM (provider: none). Cheap way to catch low-quality output before a critic round.
"""

from __future__ import annotations

from ..sandbox.driver import SandboxHandle
from .base import BaseTool, ToolContext

_DETECTORS: list[tuple[str, list[str]]] = [
    ("ruff.toml", ["ruff", "check", "."]),
    ("pyproject.toml", ["ruff", "check", "."]),
    (".eslintrc.json", ["npx", "--no-install", "eslint", "."]),
    (".eslintrc.js", ["npx", "--no-install", "eslint", "."]),
    ("go.mod", ["gofmt", "-l", "."]),
]


class LintTool(BaseTool):
    name = "lint"
    cacheable = False

    def __init__(self, ctx: ToolContext, handle: SandboxHandle) -> None:
        super().__init__(ctx)
        self.handle = handle

    async def _detect(self) -> list[str] | None:
        files = set(await self.ctx.sandbox.list_files(self.handle, self.handle.workspace_path))
        names = {f.rsplit("/", 1)[-1] for f in files}
        for marker, cmd in _DETECTORS:
            if marker in names:
                return cmd
        return None

    async def run(self, *, timeout_s: int = 60) -> dict:
        await self._guard()
        cmd = await self._detect()
        if cmd is None:
            return {"detected": False, "clean": None, "command": None, "violations": ""}
        res = await self.ctx.sandbox.exec(self.handle, cmd, timeout_s=timeout_s)
        clean = res.exit_code == 0 and not res.stdout.strip()
        return {
            "detected": True,
            "clean": clean,
            "command": " ".join(cmd),
            "violations": (res.stdout + "\n" + res.stderr)[-4000:],
        }
