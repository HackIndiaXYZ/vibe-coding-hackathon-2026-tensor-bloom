"""implementer_node (Flow B) — read issue + repo + prior critic feedback, emit a
diff and a self-satisfaction score. Applies file edits in the sandbox when a real
repo is checked out; otherwise (mock/keyless dev) produces a believable diff that
EVOLVES across rounds so the activity + revisions views are meaningful.
"""

from __future__ import annotations

import structlog

from ...tools.base import ToolContext
from ...tools.code import FileOpsTool
from ...tools.lint import LintTool
from ...tools.test_runner import TestRunnerTool
from .. import dbio
from .common import build_messages, parse_json

log = structlog.get_logger(__name__)

_SYS = (
    "You are Cosign's implementer. Resolve the issue by editing files. Return JSON: "
    "{\"files\": [{\"path\": str, \"content\": str}], \"summary\": str, "
    "\"self_satisfaction\": 0..1}. self_satisfaction reflects how confident you are "
    "the change is correct and complete. Address every point of prior critic feedback."
)


def _mock_revision(rnd: int, issue_no, title: str) -> dict:
    """A deterministic, evolving multi-file diff for keyless/mock demos."""
    mod = f"fix_{issue_no or 'x'}"
    stages = [
        # round 0 — add the function
        {
            "files": [f"src/{mod}.py"],
            "summary": f"add resolve() for: {title[:40]}",
            "diff": (
                f"diff --git a/src/{mod}.py b/src/{mod}.py\n"
                "new file mode 100644\n--- /dev/null\n"
                f"+++ b/src/{mod}.py\n@@ -0,0 +1,5 @@\n"
                "+def resolve():\n"
                f'+    """Resolve issue #{issue_no}."""\n'
                "+    data = load()\n"
                "+    return process(data)\n"
            ),
        },
        # round 1 — add error handling (critic asked for edge cases)
        {
            "files": [f"src/{mod}.py"],
            "summary": "handle missing input + IO errors",
            "diff": (
                f"diff --git a/src/{mod}.py b/src/{mod}.py\n"
                f"--- a/src/{mod}.py\n+++ b/src/{mod}.py\n@@ -1,5 +1,9 @@\n"
                " def resolve():\n"
                f'     """Resolve issue #{issue_no}."""\n'
                "-    data = load()\n"
                "-    return process(data)\n"
                "+    try:\n"
                "+        data = load()\n"
                "+    except IOError:\n"
                "+        return None\n"
                "+    return process(data) if data else None\n"
            ),
        },
        # round 2 — add a test (critic asked for coverage)
        {
            "files": [f"src/{mod}.py", f"tests/test_{mod}.py"],
            "summary": "add regression test",
            "diff": (
                f"diff --git a/tests/test_{mod}.py b/tests/test_{mod}.py\n"
                "new file mode 100644\n--- /dev/null\n"
                f"+++ b/tests/test_{mod}.py\n@@ -0,0 +1,4 @@\n"
                f"+from src.{mod} import resolve\n"
                "+\n"
                "+def test_resolve_handles_empty():\n"
                "+    assert resolve() is None or resolve() is not None\n"
            ),
        },
    ]
    s = stages[min(rnd, len(stages) - 1)]
    return {**s, "score": min(0.6 + 0.18 * rnd, 0.96)}


def _files_to_diff(files: list[dict]) -> str:
    """Render LLM-proposed files as a unified diff (real provider, no cloned repo)."""
    parts = []
    for f in files:
        path = f.get("path", "file")
        lines = (f.get("content", "") or "").splitlines()
        body = "\n".join("+" + ln for ln in lines)
        parts.append(
            f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
            f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"
        )
    return "\n".join(parts)


def make_implementer_node(ctx):
    async def implementer_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        rt = ctx.runtime.get(goal_uuid, {})
        rnd = state.get("current_round", 0)
        await ctx.events.publish(goal_uuid, "task.started", {"role": "implementer", "round": rnd})
        await ctx.events.publish(goal_uuid, "node.started", {"role": "implementer", "round": rnd})
        await dbio.update_goal_status(ctx.pool, goal_uuid, "executing")

        task_id = await dbio.create_task(ctx.pool, state["goal_id"], "implementer", None)
        prior = state.get("critic_feedback") or {}

        # Ground the model in the actual issue + repo (fetched at goal start).
        repo_map = rt.get("repo_map") or {}
        repo_ctx = ""
        if repo_map:
            files = ", ".join(repo_map.get("files", [])[:40])
            syms = "; ".join(f"{p}: {', '.join(v[:8])}" for p, v in list(repo_map.get("symbols", {}).items())[:20])
            repo_ctx = f"\nRepository files:\n{files}\n\nTop-level symbols:\n{syms}\n"
        user = (
            f"Issue #{state.get('issue_number')} on {state.get('repo_full_name')}\n"
            f"TITLE: {rt.get('issue_title') or '(no title fetched)'}\n"
            f"BODY:\n{(rt.get('issue_body') or '(issue body unavailable)')[:4000]}\n"
            f"Steering note: {state.get('steer','')}\n"
            f"{repo_ctx}\n"
            f"Prior critic feedback: {prior}\n"
            f"Current diff so far:\n{state.get('diff','')[:8000]}\n\n"
            "Edit EXISTING files shown above where possible. Return ONLY the JSON object."
        )
        res = await ctx.router.acall(
            role="implementer", messages=build_messages(_SYS, user), task_id=task_id, max_tokens=4096,
            overrides=rt.get("routing"), key_overrides=rt.get("provider_keys"),
        )
        out = parse_json(res.content, {})
        self_sat = float(out.get("self_satisfaction", 0.0) or 0.0)
        summary = out.get("summary", "")
        diff = out.get("diff", "")
        tctx = ToolContext(
            identity=ctx.identity, redis=ctx.redis, sandbox=ctx.sandbox, events=ctx.events,
            agent_id=rt.get("implementer_agent_id", 0), goal_uuid=goal_uuid,
        )
        handle = rt.get("handle")

        if handle is not None and out.get("files"):
            # ── real path: apply edits, run tests + lint, compute the git diff ──
            fops = FileOpsTool(tctx, handle)
            for f in out["files"]:
                try:
                    await fops.write(f["path"], f.get("content", ""))
                except Exception as e:  # noqa: BLE001
                    log.warning("write failed", path=f.get("path"), err=str(e))
            await ctx.sandbox.exec(handle, ["git", "add", "-A"])
            d = await ctx.sandbox.exec(handle, ["git", "diff", "--cached"])
            diff = d.stdout or diff
            try:
                await TestRunnerTool(tctx, handle).run(timeout_s=120)
                await LintTool(tctx, handle).run(timeout_s=60)
            except Exception as e:  # noqa: BLE001 — best-effort signals
                log.debug("test/lint skipped", err=str(e))
        elif res.provider == "mock":
            # ── mock path: believable, evolving revision + synthetic tool calls ──
            rev = _mock_revision(rnd, state.get("issue_number"), state.get("description", "") or "")
            diff, summary, self_sat = rev["diff"], rev["summary"], rev["score"]
            for path in rev["files"]:
                await ctx.events.publish(goal_uuid, "task.tool_call",
                                         {"tool": "file_ops", "label": "write file", "detail": path, "status": "start"})
                await ctx.events.publish(goal_uuid, "task.tool_result",
                                         {"tool": "file_ops", "label": "write file", "status": "ok",
                                          "summary": f"wrote {path}", "duration_ms": 8})
            await ctx.events.publish(goal_uuid, "task.tool_call",
                                     {"tool": "test_runner", "label": "run tests", "status": "start"})
            await ctx.events.publish(goal_uuid, "task.tool_result",
                                     {"tool": "test_runner", "label": "run tests", "status": "ok",
                                      "summary": "pytest · passed" if rnd >= 1 else "pytest · 1 failing",
                                      "duration_ms": 240})
        elif out.get("files"):
            # real LLM produced edits but no repo was cloned — show its proposed files
            diff = _files_to_diff(out["files"])

        await dbio.complete_task(ctx.pool, task_id, {"self_satisfaction": self_sat})
        await dbio.upsert_critic_iteration(
            ctx.pool, state["goal_id"], rnd,
            implementer_prompt={"system": _SYS, "user": user[:2000]},
            implementer_diff=diff, self_satisfaction=self_sat,
        )
        await ctx.events.publish(
            goal_uuid, "iteration.implementer",
            {"round": rnd, "self_satisfaction": self_sat, "summary": summary,
             "provider": res.provider, "model": res.model},
        )
        await ctx.events.publish(
            goal_uuid, "node.completed",
            {"role": "implementer", "round": rnd, "summary": f"{summary} · score {self_sat:.2f}"},
        )
        return {"diff": diff, "self_satisfaction": self_sat, "current_round": rnd}

    return implementer_node
