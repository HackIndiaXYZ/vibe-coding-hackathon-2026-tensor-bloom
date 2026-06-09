"""GitHub tool — acts AS the invoking user via their OAuth token (never a bot).

The token is passed in from AgentState.user_oauth_token (fetched from cosign-api's
identity service at goal start). Reads can be cached; writes never are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog
from githubkit import GitHub

from .base import BaseTool, ToolContext

log = structlog.get_logger(__name__)

_PR_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<num>\d+)")
_ISSUE_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<num>\d+)")


@dataclass
class GHTarget:
    owner: str
    repo: str
    number: int


def parse_pr_url(url: str) -> GHTarget | None:
    m = _PR_RE.search(url)
    return GHTarget(m["owner"], m["repo"], int(m["num"])) if m else None


def parse_issue_url(url: str) -> GHTarget | None:
    m = _ISSUE_RE.search(url)
    return GHTarget(m["owner"], m["repo"], int(m["num"])) if m else None


class GithubTool(BaseTool):
    name = "github_ops"
    cacheable = True

    def __init__(self, ctx: ToolContext, token: str) -> None:
        super().__init__(ctx)
        self._token = token

    def _client(self) -> GitHub:
        return GitHub(self._token)

    # ── reads ────────────────────────────────────────────────────────────────
    async def get_pr_diff(self, owner: str, repo: str, number: int) -> str:
        await self._guard()
        async with self.track("fetch PR diff", detail=f"{owner}/{repo}#{number}") as step:
            key = self._cache_key({"op": "pr_diff", "owner": owner, "repo": repo, "n": number})
            if (hit := await self._cache_get(key)) is not None:
                step["summary"] = "cached"
                return hit["diff"]
            gh = self._client()
            resp = await gh.arequest(
                "GET", f"/repos/{owner}/{repo}/pulls/{number}",
                headers={"Accept": "application/vnd.github.diff"},
            )
            diff = resp.text
            step["summary"] = f"{len(diff.splitlines())} lines"
            await self._cache_put(key, {"diff": diff})
            return diff

    async def get_pr_meta(self, owner: str, repo: str, number: int) -> dict:
        await self._guard()
        gh = self._client()
        pr = (await gh.rest.pulls.async_get(owner, repo, number)).parsed_data
        return {
            "title": pr.title,
            "body": pr.body or "",
            "head_ref": pr.head.ref,
            "base_ref": pr.base.ref,
            "head_repo_clone_url": pr.head.repo.clone_url if pr.head.repo else "",
            "changed_files": pr.changed_files,
        }

    async def get_issue(self, owner: str, repo: str, number: int) -> dict:
        await self._guard()
        async with self.track("fetch issue", detail=f"{owner}/{repo}#{number}") as step:
            gh = self._client()
            issue = (await gh.rest.issues.async_get(owner, repo, number)).parsed_data
            step["summary"] = (issue.title or "")[:60]
            return {"title": issue.title, "body": issue.body or "", "number": number}

    async def get_file(self, owner: str, repo: str, path: str, ref: str = "") -> str:
        await self._guard()
        gh = self._client()
        try:
            resp = await gh.arequest(
                "GET", f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": ref} if ref else None,
                headers={"Accept": "application/vnd.github.raw"},
            )
            return resp.text
        except Exception as e:  # noqa: BLE001
            raise FileNotFoundError(f"{path}: {e}") from e

    async def get_repo_default_branch(self, owner: str, repo: str) -> str:
        await self._guard()
        gh = self._client()
        r = (await gh.rest.repos.async_get(owner, repo)).parsed_data
        return r.default_branch

    # ── writes (never cached; authored by the user) ──────────────────────────
    async def open_pr(
        self, owner: str, repo: str, *, title: str, head: str, base: str, body: str
    ) -> dict:
        await self._guard()
        async with self.track("open PR", detail=f"{owner}/{repo}") as step:
            gh = self._client()
            pr = (await gh.rest.pulls.async_create(
                owner, repo, title=title, head=head, base=base, body=body
            )).parsed_data
            step["summary"] = f"#{pr.number} opened"
            await self._audit("github_open_pr", {"owner": owner, "repo": repo, "url": pr.html_url})
            return {"url": pr.html_url, "number": pr.number}

    async def post_pr_review(
        self, owner: str, repo: str, number: int, *, body: str, event: str = "COMMENT"
    ) -> dict:
        await self._guard()
        gh = self._client()
        review = (await gh.rest.pulls.async_create_review(
            owner, repo, number, body=body, event=event
        )).parsed_data
        await self._audit("github_post_review", {"owner": owner, "repo": repo, "n": number})
        return {"id": review.id}

    async def ensure_fork(self, owner: str, repo: str) -> dict:
        """Fork-mode (deferred in MVP). Idempotent fork into the user's account."""
        await self._guard()
        gh = self._client()
        fork = (await gh.rest.repos.async_create_fork(owner, repo)).parsed_data
        return {"full_name": fork.full_name, "clone_url": fork.clone_url, "owner": fork.owner.login}
