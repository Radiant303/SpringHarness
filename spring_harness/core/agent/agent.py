"""用于定义agent能力"""

from pydantic_ai import Agent
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.toolsets import ApprovalRequiredToolset
from pathlib import Path
from os import PathLike

from pydantic_ai_harness import FileSystem

from spring_harness.core.config.model import get_model


class SpringAgent:
    def __init__(self, root_dir: str | PathLike[str] | Path = ".") -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.fs_toolset = FileSystem(root_dir=str(self.root_dir)).get_toolset()
        self.approval_fs = ApprovalRequiredToolset(
            self.fs_toolset,
            approval_required_func=lambda ctx, tool_def, args: tool_def.name in {"edit_file", "write_file"},
        )

        self.agent = Agent(
            get_model(),
            toolsets=[self.approval_fs],
            output_type=[str, DeferredToolRequests],
        )

    async def get_agent(self) -> Agent[object, DeferredToolRequests | str]:
        return self.agent


cap_agent = SpringAgent().agent
