from spring_harness.core.agent.agent import cap_agent
from spring_harness.core.services.acp_server import run_acp_server


def main() -> None:
    run_acp_server(cap_agent)
