"""work 容量配额：引擎侧写文件前的最后一道闸。

云端会话挂载时把 workspace → work_id 登记进本模块（register_workspace）；
全局 hooks 的 before_tool_execute 对登记过的 workspace 做容量检查，
超出上限的写类工具调用以工具错误的形式回到模型侧，由模型告知用户。
本地 CLI / ACP 会话不登记，天然不受配额约束。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from spring_harness.core.config.settings import config
from spring_harness.core.hooks.model import hooks

# 目录大小缓存有效期：5 秒内重复检查直接复用，写工具调用频繁时避免反复遍历
_CACHE_TTL_SECONDS = 5.0

# 可能产生磁盘写入的工具，逐一过闸；只读工具（read_file 等）不拦
_WRITE_TOOLS = frozenset({
    "write_file",
    "edit_file",
    "create_directory",
    "run_command",
    "run_code",
    "save_unit",
    "run_background",
})

_workspaces: dict[str, str] = {}
_sizes: dict[str, tuple[float, int]] = {}
_lock = threading.Lock()


class WorkQuotaExceeded(RuntimeError):
    """work 目录超出容量上限，拒绝写入。"""


def register_workspace(workspace: Path, work_id: str) -> None:
    """登记 workspace 与 work 的对应关系；同一 work 的多个会话共享目录，后登记者覆盖。"""
    with _lock:
        _workspaces[str(Path(workspace).resolve())] = work_id


def unregister_workspace(workspace: Path) -> None:
    """会话卸载时摘除登记（目录大小缓存一并清掉）。"""
    key = str(Path(workspace).resolve())
    with _lock:
        work_id = _workspaces.pop(key, None)
        if work_id is not None:
            _sizes.pop(work_id, None)


def directory_size_bytes(root: Path) -> int:
    """递归求目录字节和；不可读的子项按 0 计。"""
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def check_quota(workspace: Path) -> None:
    """写工具调用前检查：workspace 已登记且目录占用超上限时抛 WorkQuotaExceeded。"""
    key = str(Path(workspace).resolve())
    with _lock:
        work_id = _workspaces.get(key)
    if work_id is None:
        return
    max_bytes = config.cloud.work_max_bytes
    now = time.monotonic()
    with _lock:
        cached = _sizes.get(work_id)
    if cached is not None and now - cached[0] <= _CACHE_TTL_SECONDS:
        size = cached[1]
    else:
        size = directory_size_bytes(Path(key))
        with _lock:
            _sizes[work_id] = (now, size)
    if size >= max_bytes:
        raise WorkQuotaExceeded(
            f"项目目录已达容量上限（{max_bytes / 1024 / 1024:.0f}MB，当前 {size / 1024 / 1024:.1f}MB），"
            "请删除项目内文件，或删除该项目后新建"
        )


@hooks.on.before_tool_execute
async def _quota_gate(
    ctx: Any, *, call: Any, tool_def: Any, args: Any,
) -> Any:
    """全局工具闸：workspace 已登记的会话，写类工具先过容量检查。"""
    workspace = getattr(getattr(ctx, "deps", None), "workspace", None)
    if workspace is None or tool_def.name not in _WRITE_TOOLS:
        return args
    check_quota(Path(workspace))
    return args
