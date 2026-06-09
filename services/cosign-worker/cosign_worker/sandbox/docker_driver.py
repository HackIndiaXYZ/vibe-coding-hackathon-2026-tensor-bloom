"""DockerDriver — v1 SandboxDriver over the local Docker daemon (ARCHITECTURE §6.2).

One ephemeral container per task. Resource-limited, readonly root + tmpfs
workspace, attached to an egress-restricted network. GitHub auth is injected
per git command via an in-memory http.extraheader (never written to disk or the
remote URL). A janitor reaps containers older than 30 minutes.
"""

from __future__ import annotations

import asyncio
import base64
import shlex
import time

import aiodocker
import structlog

from .driver import CommitInfo, ExecResult, SandboxHandle

log = structlog.get_logger(__name__)

_MEM_BYTES = 2 * 1024**3
_NANO_CPUS = 2 * 10**9
_PIDS_LIMIT = 512
_AGENT_UID = 1000
_REAP_AGE_S = 30 * 60
_WORKDIR = "/workspace"


def _auth_header(token: str) -> str:
    """Build an `http.extraheader` value: Authorization: Basic b64(x-access-token:TOKEN)."""
    raw = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return f"http.extraheader=Authorization: Basic {raw}"


class DockerDriver:
    def __init__(self, *, image: str, network: str) -> None:
        self._image = image
        self._network = network
        self._docker = aiodocker.Docker()
        self._containers: dict[str, float] = {}  # container_id -> created_at

    async def close(self) -> None:
        await self._docker.close()

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def start(
        self,
        task_id: str,
        image: str,
        repo_url: str,
        branch: str,
        github_token: str,
        *,
        timeout_s: int = 30,
    ) -> SandboxHandle:
        name = f"cosign-sbx-{task_id}-{int(time.time())}"
        config = {
            "Image": image or self._image,
            "Cmd": ["sleep", "infinity"],
            "User": "agent",
            "WorkingDir": _WORKDIR,
            "Env": ["HOME=/workspace", "GIT_CONFIG_GLOBAL=/workspace/.gitconfig"],
            "HostConfig": {
                "Memory": _MEM_BYTES,
                "NanoCpus": _NANO_CPUS,
                "PidsLimit": _PIDS_LIMIT,
                "ReadonlyRootfs": True,
                "Tmpfs": {
                    "/tmp": "size=512m,exec",
                    "/workspace": f"size=1g,uid={_AGENT_UID},gid={_AGENT_UID},exec",
                },
                "NetworkMode": self._network,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "AutoRemove": False,
            },
        }
        container = await self._docker.containers.create(config=config, name=name)
        await container.start()
        created = time.time()
        self._containers[container.id] = created

        handle = SandboxHandle(
            id=name,
            container_id=container.id,
            workspace_path=_WORKDIR,
            repo_url=repo_url,
            branch=branch,
            created_at=created,
        )

        if repo_url:
            await self._clone(handle, repo_url, branch, github_token, timeout_s=max(timeout_s, 120))
        return handle

    async def stop(self, handle: SandboxHandle) -> None:
        self._containers.pop(handle.container_id, None)
        try:
            container = await self._docker.containers.get(handle.container_id)
            await container.delete(force=True)
        except aiodocker.exceptions.DockerError as e:  # already gone
            log.debug("stop: container delete failed", err=str(e))

    async def reap_stale(self) -> int:
        """Delete containers older than _REAP_AGE_S. Returns count reaped."""
        now = time.time()
        stale = [cid for cid, born in self._containers.items() if now - born > _REAP_AGE_S]
        for cid in stale:
            try:
                c = await self._docker.containers.get(cid)
                await c.delete(force=True)
            except aiodocker.exceptions.DockerError:
                pass
            self._containers.pop(cid, None)
        return len(stale)

    # ── exec ─────────────────────────────────────────────────────────────────
    async def exec(
        self,
        handle: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        timeout_s: int = 30,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        container = await self._docker.containers.get(handle.container_id)
        start = time.time()
        ex = await container.exec(
            cmd,
            stdout=True,
            stderr=True,
            workdir=cwd or handle.workspace_path,
            environment=env or {},
            user="agent",
        )
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []

        async def _pump() -> None:
            stream = ex.start(detach=False)
            async with stream:
                while True:
                    msg = await stream.read_out()
                    if msg is None:
                        break
                    (out_chunks if msg.stream == 1 else err_chunks).append(msg.data)

        try:
            await asyncio.wait_for(_pump(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return ExecResult(124, b"".join(out_chunks).decode(errors="replace"),
                              "timeout", time.time() - start)

        info = await ex.inspect()
        return ExecResult(
            exit_code=int(info.get("ExitCode") or 0),
            stdout=b"".join(out_chunks).decode(errors="replace"),
            stderr=b"".join(err_chunks).decode(errors="replace"),
            duration_s=time.time() - start,
        )

    # ── files (base64 for binary safety, no stdin needed) ────────────────────
    async def read_file(self, handle: SandboxHandle, path: str) -> bytes:
        res = await self.exec(handle, ["base64", "-w0", path])
        if res.exit_code != 0:
            raise FileNotFoundError(f"{path}: {res.stderr.strip()}")
        return base64.b64decode(res.stdout)

    async def write_file(self, handle: SandboxHandle, path: str, content: bytes) -> None:
        b64 = base64.b64encode(content).decode()
        script = (
            f"mkdir -p \"$(dirname {shlex.quote(path)})\" && "
            f"printf '%s' {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}"
        )
        res = await self.exec(handle, ["sh", "-c", script])
        if res.exit_code != 0:
            raise OSError(f"write {path} failed: {res.stderr.strip()}")

    async def list_files(
        self, handle: SandboxHandle, path: str, *, recursive: bool = False
    ) -> list[str]:
        cmd = ["find", path, "-type", "f"] if recursive else ["ls", "-1", path]
        res = await self.exec(handle, cmd)
        if res.exit_code != 0:
            return []
        return [ln for ln in res.stdout.splitlines() if ln]

    # ── git ──────────────────────────────────────────────────────────────────
    async def _clone(
        self, handle: SandboxHandle, repo_url: str, branch: str, token: str, *, timeout_s: int
    ) -> None:
        args = ["git", "-c", _auth_header(token), "clone", "--depth", "50"]
        if branch:
            args += ["--branch", branch]
        args += [repo_url, handle.workspace_path]
        # clone into the workspace (must be empty); workspace tmpfs is empty at start
        res = await self.exec(handle, args, cwd="/", timeout_s=timeout_s)
        if res.exit_code != 0:
            raise RuntimeError(f"clone failed: {res.stderr.strip()}")

    async def commit_and_push(
        self,
        handle: SandboxHandle,
        branch: str,
        message: str,
        *,
        force: bool = False,
    ) -> CommitInfo:
        # Auth is supplied per-push via an in-memory header (see push()); commit
        # is local and needs no token.
        steps = [
            ["git", "config", "user.email", "cosign@users.noreply.github.com"],
            ["git", "config", "user.name", "Cosign (on behalf of user)"],
            ["git", "checkout", "-B", branch],
            ["git", "add", "-A"],
            ["git", "commit", "-m", message, "--allow-empty"],
        ]
        for step in steps:
            res = await self.exec(handle, step)
            if res.exit_code != 0 and step[1] != "commit":
                raise RuntimeError(f"{' '.join(step)} failed: {res.stderr.strip()}")
        sha_res = await self.exec(handle, ["git", "rev-parse", "HEAD"])
        sha = sha_res.stdout.strip()
        return CommitInfo(sha=sha, branch=branch, pushed=False)

    async def push(
        self, handle: SandboxHandle, branch: str, token: str, *, remote: str = "origin",
        force: bool = False, timeout_s: int = 120,
    ) -> None:
        """Push a branch using an in-memory auth header (token never on disk)."""
        push_cmd = ["push"]
        if force:
            push_cmd.append("--force")  # must come AFTER the `push` subcommand
        push_cmd += [remote, f"HEAD:{branch}"]
        args = ["git", "-c", _auth_header(token), *push_cmd]
        res = await self.exec(handle, args, timeout_s=timeout_s)
        if res.exit_code != 0:
            raise RuntimeError(f"push failed: {res.stderr.strip()}")
