"""test_runner — detect the repo's test command, run it in the sandbox, parse pass/fail.

No LLM (provider: none). Lets the critic check claims like "tests pass".
"""

from __future__ import annotations

from ..sandbox.driver import SandboxHandle
from .base import BaseTool, ToolContext

# (marker file, command) — first match wins. Makefile is checked first so a
# repo's own `make test` target wins over a language default.
_DETECTORS: list[tuple[str, list[str]]] = [
    ("Makefile", ["make", "test"]),
    ("pytest.ini", ["python3", "-m", "pytest", "-q"]),
    ("pyproject.toml", ["python3", "-m", "pytest", "-q"]),
    ("package.json", ["npm", "test", "--silent"]),
    ("go.mod", ["go", "test", "./..."]),
    ("Cargo.toml", ["cargo", "test"]),
]


class TestRunnerTool(BaseTool):
    __test__ = False  # not a pytest test class
    name = "test_runner"
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

    async def run(self, *, timeout_s: int = 120) -> dict:
        await self._guard()
        cmd = await self._detect()
        if cmd is None:
            return {"detected": False, "passed": None, "command": None, "output": "no test command detected"}
        res = await self.ctx.sandbox.exec(self.handle, cmd, timeout_s=timeout_s)
        passed = res.exit_code == 0
        await self._audit("test_runner", {"command": cmd, "passed": passed})
        return {
            "detected": True,
            "passed": passed,
            "command": " ".join(cmd),
            "output": (res.stdout + "\n" + res.stderr)[-4000:],
        }
