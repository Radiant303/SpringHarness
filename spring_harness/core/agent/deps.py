from dataclasses import dataclass
from pathlib import Path

from spring_harness.utils.monitor_file import DirectoryMonitor


@dataclass
class CodingAgentDeps:
    workspace: Path
    monitor: DirectoryMonitor

    @classmethod
    def create_default(cls, workspace: Path | None = None):
        workspace = (workspace or Path.cwd()).resolve()
        monitor = DirectoryMonitor(workspace)
        monitor.start()
        return cls(
            workspace=workspace,
            monitor=monitor,
        )
