"""用于定义agent能力"""

from pydantic_ai import Agent
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.toolsets import ApprovalRequiredToolset
from pydantic_ai_harness import FileSystem, Shell

from spring_harness.core.config.model import get_model


def command_filter(command:str)->bool:
    forbidden = [
        "rm",
        "rmdir",
        "del",
        "erase",
        "mkfs",
        "format",
        "shutdown",
        "reboot",
        "poweroff",
        "dd",
        "diskpart",
    ]

    cmd = command.lower()

    return not any(
        cmd.startswith(x) or f" {x} " in cmd
        for x in forbidden
    )

# 文件读写编辑：edit_file/write_file 的结构化参数是 diff 展示的数据源；
# 写操作挂起等人工批准（DeferredToolRequests），读操作自动放行
fs_toolset = FileSystem(root_dir="./").get_toolset()
approval_fs = ApprovalRequiredToolset(
    fs_toolset,
    approval_required_func=lambda ctx, tool_def, args: tool_def.name in {"edit_file", "write_file"},
)

# output_type 含 DeferredToolRequests：有调用被挂起时 run 的输出就是它而不是 str
cap_agent = Agent(
    get_model(),
    toolsets=[approval_fs],
    output_type=[str, DeferredToolRequests],
)


__all__ = ['cap_agent']
