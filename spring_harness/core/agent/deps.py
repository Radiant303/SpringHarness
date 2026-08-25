from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodingAgentDeps:
    workspace: Path

    @classmethod
    def create_default(cls, workspace: Path | None) -> "CodingAgentDeps":
        """创建默认配置的依赖"""
        if workspace is None:
            workspace = Path.cwd()
        return cls(workspace=workspace)

deps = CodingAgentDeps.create_default
