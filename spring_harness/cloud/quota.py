"""work 容量配额：引擎侧写文件前的最后一道闸。

云端会话挂载时把 workspace → work_id 登记进本模块（register_workspace）；
全局 hooks 的 before_tool_execute 对登记过的 workspace 做容量检查，
超出上限的写类工具调用以工具错误的形式回到模型侧，由模型告知用户。
本地 CLI / ACP 会话不登记，天然不受配额约束。

上限取值：经内部 API 取解析好的生效值（用户覆盖优先，否则全局设置），
30 秒 TTL 缓存；网关不可达或响应缺值时 fail-open 放行，不阻断写工具。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from spring_harness.core.hooks.model import hooks

# 目录大小缓存有效期：5 秒内重复检查直接复用，写工具调用频繁时避免反复遍历
_CACHE_TTL_SECONDS = 5.0

# 生效上限缓存有效期：管理员调整后最多 30 秒在引擎侧生效
_LIMIT_TTL_SECONDS = 30.0

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
_limits: dict[str, tuple[float, int]] = {}
_lock = threading.Lock()


class WorkQuotaExceeded(RuntimeError):
    """work 目录超出容量上限，拒绝写入。"""


def register_workspace(workspace: Path, work_id: str) -> None:
    """登记 workspace 与 work 的对应关系；同一 work 的多个会话共享目录，后登记者覆盖。"""
    with _lock:
        _workspaces[str(Path(workspace).resolve())] = work_id


def unregister_workspace(workspace: Path) -> None:
    """会话卸载时摘除登记（目录大小与上限缓存一并清掉）。"""
    key = str(Path(workspace).resolve())
    with _lock:
        work_id = _workspaces.pop(key, None)
        if work_id is not None:
            _sizes.pop(work_id, None)
            _limits.pop(work_id, None)


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


def _effective_max_bytes(work_id: str) -> int | None:
    """取该 work 生效的单工作区上限；网关不可达或响应缺值时返回 None（调用方放行）。"""
    now = time.monotonic()
    with _lock:
        cached = _limits.get(work_id)
    if cached is not None and now - cached[0] <= _LIMIT_TTL_SECONDS:
        return cached[1]
    # 函数内导入，避免模块级循环依赖
    from spring_harness.cloud import gateway_store

    try:
        row = gateway_store.get_work(work_id)
    except Exception:  # noqa: BLE001 网关不可达时放行，不阻断写工具
        return None
    if row is None or row.work_max_bytes <= 0:
        return None
    with _lock:
        _limits[work_id] = (now, row.work_max_bytes)
    return row.work_max_bytes


def check_quota(workspace: Path) -> None:
    """写工具调用前检查：workspace 已登记且目录占用超上限时抛 WorkQuotaExceeded。"""
    key = str(Path(workspace).resolve())
    with _lock:
        work_id = _workspaces.get(key)
    if work_id is None:
        return
    max_bytes = _effective_max_bytes(work_id)
    if max_bytes is None:
        return
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
            "请删除项目内文件，或联系管理员调整上限"
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
