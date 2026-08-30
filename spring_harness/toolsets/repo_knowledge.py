import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable
from enum import IntEnum
from functools import wraps
from pathlib import Path
from typing import TypeVar

from pydantic_ai import ApprovalRequiredToolset, FunctionToolset, ModelRetry

KNOWLEDGE_PATH = Path.home() / ".springharness" / "knowledge"


# 可恢复的错误类型
_RECOVERABLE_ERRORS = (
    ValueError,
    FileNotFoundError,
    PermissionError,
    NotADirectoryError,
    IsADirectoryError
)

"""
给知识分为三类：
陈述性知识（“是什么”）：关于事实、概念和原理的描述。比如“苏州是江苏的城市”、“勾股定理的公式”。
程序性知识（“怎么做”）：关于技能、步骤和方法。比如“如何骑自行车”、“如何解一道方程式”。
条件性知识（“何时做/为何做”）：关于策略和情境判断，知道在什么条件下使用哪种程序。比如“在考试时间不够时，先做哪类题”。
"""
class KnowledgeType(IntEnum):
    """知识类型"""
    DECLARATIVE = 1
    PROCEDURAL = 2
    CONDITIONAL = 3


# Markdown 单行标题：# ~ ######，# 后必须跟空白
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

def _hash_content(content: str) -> str:
    """计算知识文件内容的哈希值，用于乐观并发控制"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

# unified diff 的 hunk 头：@@ -起始行,行数 +起始行,行数 @@（行数可省略，默认为 1）
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")

def _apply_diff(file_lines: list[str], diff: str) -> tuple[list[str], int]:
    """将 unified diff 按声明行号应用到文件行列表，返回 (新行列表, hunk 数)

    diff 只接受纯 hunk 内容（@@ 头、空格/- /+ 开头的行），其他内容报错。
    """
    lines = diff.splitlines()
    i = 0
    delta = 0  # 已应用的 hunk 造成的行数偏移
    count = 0
    while i < len(lines):
        m = _HUNK_RE.match(lines[i])
        if not m:
            raise ValueError(f"无法解析的行: {lines[i]!r}，diff 中只能包含 @@ hunk 内容")
        start = int(m.group(1)) - 1 + delta
        i += 1
        old: list[str] = []
        new: list[str] = []
        while i < len(lines) and lines[i][:1] in (" ", "-", "+"):
            if lines[i][0] in (" ", "-"):
                old.append(lines[i][1:])
            if lines[i][0] in (" ", "+"):
                new.append(lines[i][1:])
            i += 1
        if not old:
            start += 1  # @@ -n,0 ... 表示在第 n 行之后插入
        if file_lines[start:start + len(old)] != old:
            raise ValueError(
                f"补丁内容与文件第 {m.group(1)} 行起的内容不匹配，请重新读取文件后再生成补丁"
            )
        file_lines[start:start + len(old)] = new
        delta += len(new) - len(old)
        count += 1
    if count == 0:
        raise ValueError("diff 中没有任何 hunk（@@ ... @@）")
    return file_lines, count

T = TypeVar('T')

def _recoverable[T](fn: Callable[..., T | Awaitable[T]]) -> Callable[..., T | Awaitable[T]]:
    """支持同步和异步函数的装饰器"""

    if inspect.iscoroutinefunction(fn):
        @wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except _RECOVERABLE_ERRORS as e:
                raise ModelRetry(str(e)) from e
        return async_wrapper
    else:
        @wraps(fn)
        def sync_wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except _RECOVERABLE_ERRORS as e:
                raise ModelRetry(str(e)) from e
        return sync_wrapper

class KnowledgeStore:
    def __init__(self):
        self._declarative:Path = KNOWLEDGE_PATH / "declarative.md"
        self._procedural:Path = KNOWLEDGE_PATH / "procedural.md"
        self._conditional:Path = KNOWLEDGE_PATH / "conditional.md"
        self._ensure_directories()

    def _ensure_directories(self):
        """确保目录存在"""
        path = KNOWLEDGE_PATH
        path.mkdir(parents=True, exist_ok=True)
        self._ensure_file_exists(self._declarative)
        self._ensure_file_exists(self._procedural)
        self._ensure_file_exists(self._conditional)


    def _ensure_file_exists(self, file_path: Path) -> None:
        """确保文件存在，如果不存在则创建空文件"""
        if not file_path.exists():
            file_path.touch()

    def _file(self, type: KnowledgeType) -> Path:
        """根据知识类型返回对应的文件路径"""
        return {
            KnowledgeType.DECLARATIVE: self._declarative,
            KnowledgeType.PROCEDURAL: self._procedural,
            KnowledgeType.CONDITIONAL: self._conditional,
        }[type]

    def read_index_knowledge(self, type: KnowledgeType) -> str:
        """读取指定类型的知识索引内容。这里返回拿到的只是对于知识类型的索引内容，如果想拿到具体内容请使用read_knowledge工具。

        Args:
            type: 知识类型
        """
        path = self._file(type)
        content = path.read_text(encoding="utf-8")
        header = f"{path.name} 哈希值: {_hash_content(content)}\n目录（行号: 标题）："
        index_lines: list[str] = []
        for lineno, line in enumerate(content.splitlines(), start=1):
            m = _HEADING_RE.match(line)
            if m:
                indent = "  " * (len(m.group(1)) - 1)
                index_lines.append(f"{lineno}: {indent}{m.group(1)} {m.group(2).strip()}")
        if not index_lines:
            return f"{header}\n该知识文件暂无目录结构。"
        return f"{header}\n" + "\n".join(index_lines)


    @_recoverable
    def read_knowledge(self, type: KnowledgeType, *, offset: int = 1, limit: int | None = None) -> str:
        """读取指定类型的知识内容。

        Args:
            type: 知识类型
            offset: 起始行号（从 1 开始）
            limit: 最多读取行数，None 表示读到末尾
        """
        if offset < 1:
            raise ValueError("offset 是从 1 开始的行号，不能小于 1")
        path = self._file(type)
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        sliced = lines[offset - 1: None if limit is None else offset - 1 + limit]
        header = f"{path.name} 哈希值: {_hash_content(content)}\n"
        if not sliced:
            return f"{header}文件共 {len(lines)} 行，第 {offset} 行起没有内容。"
        header += f"第 {offset}-{offset + len(sliced) - 1} 行（共 {len(lines)} 行）：\n"
        return header + "\n".join(
            f"{lineno}: {line}" for lineno, line in enumerate(sliced, start=offset)
        )

    @_recoverable
    def edit_knowledge(self, type: KnowledgeType, diff: str, *, expected_hash: str | None = None) -> str:
        """使用 unified diff 补丁编辑知识文件。

        Args:
            type: 知识类型
            diff: unified diff 格式的补丁，只包含一个或多个 hunk（不要包含
                ```diff 代码围栏、---/+++ 文件头等额外内容）。
                hunk 以 @@ -起始行,行数 +起始行,行数 @@ 开头；上下文行以空格开头，
                删除行以 - 开头，新增行以 + 开头。示例：
                @@ -3,2 +3,3 @@
                 保持不变的上下文行
                -要删除的旧行
                +新增的第一行
                +新增的第二行
            expected_hash: 可选。提供时若与文件当前哈希值不匹配则拒绝编辑
                （乐观并发控制），此时应重新读取文件后再生成补丁。

        Returns:
            应用结果摘要和文件的新哈希值。
        """
        path = self._file(type)
        content = path.read_text(encoding="utf-8")
        if expected_hash is not None and _hash_content(content) != expected_hash:
            raise ValueError(
                "文件哈希值与 expected_hash 不匹配，说明文件在上次读取后已被修改，"
                "请重新读取文件后再生成补丁"
            )
        new_lines, count = _apply_diff(content.splitlines(), diff)
        new_content = "\n".join(new_lines)
        if content.endswith("\n") or not content:
            new_content += "\n"
        path.write_text(new_content, encoding="utf-8")
        return f"编辑成功，应用了 {count} 个 hunk。新哈希值: {_hash_content(new_content)}"

knowledge = KnowledgeStore()
read_knowledge = knowledge.read_knowledge
edit_knowledge = knowledge.edit_knowledge
read_index_knowledge = knowledge.read_index_knowledge

knowledge_toolsets = FunctionToolset(tools=[read_knowledge, edit_knowledge, read_index_knowledge])
approval_required_knowledge_toolsets = ApprovalRequiredToolset(
    knowledge_toolsets,
    approval_required_func=lambda ctx, tool, args:
        tool.name in {
            "edit_knowledge",
        },
)
