# spring_harness/capabilities/repo_context.py
from pathlib import Path

from pydantic_ai_harness import RepoContext


def repo_context(root: Path) -> RepoContext:
    """加载工作区的 CLAUDE.md/AGENTS.md 等仓库上下文（向上追溯到工作区为止）。"""
    return RepoContext(workspace_dir=root)
