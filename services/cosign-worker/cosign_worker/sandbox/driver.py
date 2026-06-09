"""SandboxDriver protocol + value types (ARCHITECTURE §6.1).

A driver hides *how* an isolated agent environment is run from *what* the worker
needs from it. DockerDriver is the v1 implementation; a KubernetesDriver
implements the same protocol post-hackathon. Nodes use these methods only —
never raw aiodocker — so the k8s swap is an env-var change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SandboxHandle:
    id: str  # opaque to callers
    container_id: str  # Docker container ID or k8s pod name
    workspace_path: str  # path inside the container/pod
    repo_url: str
    branch: str
    created_at: float


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float


@dataclass
class CommitInfo:
    sha: str
    branch: str
    pushed: bool


@runtime_checkable
class SandboxDriver(Protocol):
    async def start(
        self,
        task_id: str,
        image: str,
        repo_url: str,
        branch: str,
        github_token: str,
        *,
        timeout_s: int = 30,
    ) -> SandboxHandle: ...

    async def exec(
        self,
        handle: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        timeout_s: int = 30,
        env: dict[str, str] | None = None,
    ) -> ExecResult: ...

    async def read_file(self, handle: SandboxHandle, path: str) -> bytes: ...

    async def write_file(self, handle: SandboxHandle, path: str, content: bytes) -> None: ...

    async def list_files(
        self, handle: SandboxHandle, path: str, *, recursive: bool = False
    ) -> list[str]: ...

    async def commit_and_push(
        self,
        handle: SandboxHandle,
        branch: str,
        message: str,
        *,
        force: bool = False,
    ) -> CommitInfo: ...

    async def stop(self, handle: SandboxHandle) -> None: ...
