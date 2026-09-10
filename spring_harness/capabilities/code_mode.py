from pathlib import Path

from pydantic_ai_harness import CodeMode
from pydantic_monty import MountDir

from spring_harness.core.config.settings import STATE_DIR


def code_mode(root: Path) -> CodeMode:
    """Code Mode：只读工具折叠进 run_code 沙箱。

    /work 以 overlay 挂载工作区（沙箱可读写副本，改动不落盘）；
    /scratch 是可写草稿区，落盘到工作区的 .springharness/.agent-scratch/。
    """
    scratch = root / STATE_DIR / ".agent-scratch"
    scratch.mkdir(parents=True, exist_ok=True)  # MountDir 要求宿主路径存在
    return CodeMode(
        mount=[
            MountDir(virtual_path="/work", host_path=root, mode="overlay"),
            MountDir(virtual_path="/scratch", host_path=scratch, mode="read-write"),
        ],
        tools=["read_file", "search_files","find_files"],
    )
