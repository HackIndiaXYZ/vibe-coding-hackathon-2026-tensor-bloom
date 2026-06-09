"""code_exec + file_ops — run inside the sandbox via SandboxDriver (never raw aiodocker)."""

from __future__ import annotations

from ..sandbox.driver import SandboxHandle
from .base import BaseTool, ToolContext


class CodeExecTool(BaseTool):
    name = "code_exec"
    cacheable = False  # side-effectful; never cached

    def __init__(self, ctx: ToolContext, handle: SandboxHandle) -> None:
        super().__init__(ctx)
        self.handle = handle

    async def run(self, cmd: list[str], *, cwd: str | None = None, timeout_s: int = 30) -> dict:
        await self._guard()
        res = await self.ctx.sandbox.exec(self.handle, cmd, cwd=cwd, timeout_s=timeout_s)
        await self._audit("code_exec", {"cmd": cmd, "exit": res.exit_code})
        return {"exit_code": res.exit_code, "stdout": res.stdout, "stderr": res.stderr}


class FileOpsTool(BaseTool):
    name = "file_ops"
    cacheable = False

    def __init__(self, ctx: ToolContext, handle: SandboxHandle) -> None:
        super().__init__(ctx)
        self.handle = handle

    async def read(self, path: str) -> str:
        await self._guard()
        data = await self.ctx.sandbox.read_file(self.handle, path)
        return data.decode(errors="replace")

    async def write(self, path: str, content: str) -> None:
        await self._guard()
        await self.ctx.sandbox.write_file(self.handle, path, content.encode())
        await self._audit("file_write", {"path": path, "bytes": len(content)})

    async def delete(self, path: str) -> None:
        await self._guard()
        await self.ctx.sandbox.exec(self.handle, ["rm", "-f", path])
        await self._audit("file_delete", {"path": path})

    async def list(self, path: str = ".", *, recursive: bool = False) -> list[str]:
        await self._guard()
        return await self.ctx.sandbox.list_files(self.handle, path, recursive=recursive)
