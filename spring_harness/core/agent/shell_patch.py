"""Windows 兼容补丁：修复 pydantic-ai-harness ShellToolset 在 Windows 上的杀进程问题。

上游 ShellToolset._kill_process_group 用 os.killpg / os.getpgid（Unix 进程组 API），
Windows 的 os 模块没有这两个函数 —— run_command 一旦超时，kill 路径抛出
AttributeError 并向上传播。pydantic-ai 只把 ModelRetry 喂回模型重试，其它异常
直接终止整轮运行（TUI 里表现为 ❌ AttributeError: module 'os' has no attribute
'killpg'），模型根本没有重试机会。

补丁只在 Windows（os.name == "nt"）生效，杀进程改用 taskkill /F /T：

- 命令经 cmd.exe 执行（如 "cd /d D:\\test && node bench3.mjs"），进程树是
  cmd.exe → node.exe；只杀 cmd.exe 会让 node 残留（超时的 benchmark 还在后台跑，
  端口/文件还被占着），所以必须用 /T 杀整棵树；
- 超时场景恢复为返回 "[Command timed out after Ns]" 的正常工具结果，
  模型能看到并自行调整（重试 / 加大 timeout_seconds / 换命令）。

上游 0.28.0 ~ 0.30.0 均未修复（见 pydantic-ai-harness issue #349、PR #390；
macroscope/_toolset.py 有同款问题，本项目未使用）；上游支持 Windows 后删除本模块。

"""
# TODO:等框架修复后删除这个代码
import os
import subprocess

import anyio
import anyio.abc
from pydantic_ai_harness.shell._toolset import _KILL_GRACE_PERIOD, ShellToolset


async def _kill_process_windows_safe(self: ShellToolset, proc: anyio.abc.Process) -> None:
    """taskkill /F /T 强杀整棵进程树；进程已退出或 taskkill 失败则兜底 proc.kill()。

    全程 shield：用户在杀到一半时按 Esc 取消，也要保证杀完，否则残留进程会占着资源。
    """
    if proc.returncode is not None:
        return  # 进程已退出，无事可做

    with anyio.CancelScope(shield=True):
        # Windows 没有进程组信号；taskkill /T 是杀整棵树（cmd.exe → node 等）的标准做法
        try:
            killer = await anyio.open_process(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            killer = None
        if killer is not None:
            with anyio.move_on_after(_KILL_GRACE_PERIOD):
                await killer.wait()

        # 兜底：主进程还没死就再补一刀
        if proc.returncode is None:
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass

        # 等主进程退出，带上界保证 kill 路径永远不会挂住工具调用
        with anyio.move_on_after(_KILL_GRACE_PERIOD):
            await proc.wait()


if os.name == "nt":
    ShellToolset._kill_process_group = _kill_process_windows_safe  # type: ignore[method-assign]
