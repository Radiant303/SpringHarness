from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import ModelMessage, RequestUsage

from spring_harness.core.background import BackgroundTaskManager
from spring_harness.utils.monitor_file import DirectoryMonitor


@dataclass
class CodingAgentDeps:
    workspace: Path
    monitor: DirectoryMonitor
    last_messages: list[ModelMessage] = field(default_factory=list)
    usage_log: list[RequestUsage] = field(default_factory=list)
    background: BackgroundTaskManager = field(default_factory=BackgroundTaskManager)
    @classmethod
    def create_default(cls, workspace: Path | None = None):
        workspace = (workspace or Path.cwd()).resolve()
        monitor = DirectoryMonitor(workspace)
        monitor.start()
        return cls(
            workspace=workspace,
            monitor=monitor,
        )
