"""DockerDriver lifecycle test (ARCHITECTURE §6 exit criterion).

Starts a container, execs a command, writes+reads a file, lists files, stops it,
and confirms the container is gone. Skips cleanly if Docker is unavailable.
"""

from __future__ import annotations

import aiodocker
import pytest

from cosign_worker.sandbox.docker_driver import DockerDriver

IMAGE = "cosign/sandbox:latest"
NETWORK = "cosign_sandbox_net"


async def _docker_available() -> bool:
    try:
        d = aiodocker.Docker()
        await d.version()
        await d.close()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_sandbox_lifecycle():
    if not await _docker_available():
        pytest.skip("docker unavailable")

    driver = DockerDriver(image=IMAGE, network=NETWORK)
    try:
        handle = await driver.start(
            task_id="test", image=IMAGE, repo_url="", branch="", github_token=""
        )
        assert handle.container_id

        # exec
        res = await driver.exec(handle, ["echo", "ok"])
        assert res.exit_code == 0
        assert res.stdout.strip() == "ok"

        # write + read round trip (binary-safe)
        payload = b"hello cosign\n\x00\x01"
        await driver.write_file(handle, "/workspace/foo.bin", payload)
        got = await driver.read_file(handle, "/workspace/foo.bin")
        assert got == payload

        # list
        files = await driver.list_files(handle, "/workspace")
        assert any("foo.bin" in f for f in files)

        # stop + confirm gone
        cid = handle.container_id
        await driver.stop(handle)
        d = aiodocker.Docker()
        try:
            with pytest.raises(aiodocker.exceptions.DockerError):
                await d.containers.get(cid)
        finally:
            await d.close()
    finally:
        await driver.close()
