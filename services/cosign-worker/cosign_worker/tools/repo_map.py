"""repo_map — compact repo structure + top-level symbols via tree-sitter (no LLM).

Gives agents grounding without sending the whole repo as context.
"""

from __future__ import annotations

import structlog

from ..sandbox.driver import SandboxHandle
from .base import BaseTool, ToolContext

log = structlog.get_logger(__name__)

_EXT_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

_DEF_SUFFIXES = ("_definition", "_declaration", "_item", "_spec")
_MAX_FILES = 200


def _lang_for(path: str) -> str | None:
    for ext, lang in _EXT_LANG.items():
        if path.endswith(ext):
            return lang
    return None


def extract_symbols(lang: str, source: bytes) -> list[str]:
    """Pure function: top-level def/class/type names. Unit-testable.

    Uses the tree-sitter-language-pack binding (node.kind / node.child(i) /
    byte offsets — note this differs from upstream tree-sitter's node.type/.text).
    """
    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser(lang)
    except Exception as e:  # noqa: BLE001 — unknown grammar
        log.debug("no parser", lang=lang, err=str(e))
        return []

    # This binding exposes node members as methods (kind(), child_count(), ...)
    # and parse() wants str; byte offsets index the utf-8 bytes.
    def _v(x):
        return x() if callable(x) else x

    text = source.decode("utf-8", errors="replace")
    src_bytes = text.encode("utf-8")
    tree = parser.parse(text)
    root = _v(tree.root_node)

    out: list[str] = []

    def visit(node) -> None:
        if any(_v(node.kind).endswith(s) for s in _DEF_SUFFIXES):
            name = node.child_by_field_name("name")
            if name is not None:
                out.append(
                    src_bytes[_v(name.start_byte):_v(name.end_byte)].decode("utf-8", errors="replace")
                )
        for i in range(_v(node.child_count)):
            visit(node.child(i))

    visit(root)
    # de-dup, preserve order
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


class RepoMapTool(BaseTool):
    name = "repo_map"
    cacheable = True

    def __init__(self, ctx: ToolContext, handle: SandboxHandle) -> None:
        super().__init__(ctx)
        self.handle = handle

    async def run(self) -> dict:
        await self._guard()
        files = await self.ctx.sandbox.list_files(
            self.handle, self.handle.workspace_path, recursive=True
        )
        code_files = [f for f in files if _lang_for(f) and "/.git/" not in f][:_MAX_FILES]
        symbols: dict[str, list[str]] = {}
        for path in code_files:
            lang = _lang_for(path)
            if lang is None:
                continue
            try:
                src = await self.ctx.sandbox.read_file(self.handle, path)
            except FileNotFoundError:
                continue
            syms = extract_symbols(lang, src)
            if syms:
                symbols[path] = syms
        return {"files": code_files, "symbols": symbols}
