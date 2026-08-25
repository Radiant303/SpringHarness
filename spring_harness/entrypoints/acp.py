from pathlib import Path

from spring_harness.core.agent.agent import create_agent
from spring_harness.core.services.acp_server import run_acp_server


def main() -> None:
    run_acp_server(create_agent(root_dir=Path.cwd()))
