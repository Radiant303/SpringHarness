import asyncio
import subprocess
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_ai import FunctionToolset


async def subagent_antigravity(
    instruction: Annotated[
        str,
        Field(
            description=(
                "需要委派给 Antigravity 子智能体执行的代码工程任务，"
                "例如代码重构、排查修复 Bug、补充测试用例或分析当前项目代码结构。"
            )
        ),
    ],
) -> str:
    """调用本地运行的 Antigravity 智能体作为子代理执行代码工程任务。

    该工具严格绑定在当前运行的工作区目录（CWD）中执行，禁止操作其他外部路径。
    运行模式限定为受控编辑（accept-edits）与系统沙箱（sandbox），
    支持免交互自动执行已授权范围内的代码读写。
    协程被取消时（后台任务取消/会话关闭）会杀掉子进程，不留孤儿。

    Args:
        instruction: 传递给 Antigravity 子智能体的具体工作任务或提示词。

    Returns:
        str: 执行成功时返回 Antigravity 输出的 JSON 格式结果字符串；
             若执行失败或出错，返回包含退出状态码及标准错误流 (stderr) 的错误信息。
    """
    # 强制硬编码锁定为当前运行时工作目录，不接受任何外部入参篡改
    current_workspace = Path.cwd().resolve()

    cmd = [
        "agy",
        "--print", instruction,
        "--add-dir", str(current_workspace),
        "--mode", "accept-edits",
        "--sandbox",
        "--dangerously-skip-permissions",
        "--output-format", "json",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(current_workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        process.kill()
        await process.wait()  # 等子进程落地收尸，避免僵尸/句柄泄漏
        raise

    if process.returncode == 0:
        return stdout.decode("utf-8")
    else:
        return f"执行失败 (退出码: {process.returncode}): {stderr.decode('utf-8').strip()}"

local_subagents_toolset = FunctionToolset()
local_subagents_toolset.add_function(subagent_antigravity, metadata={"backgroundable": True})
