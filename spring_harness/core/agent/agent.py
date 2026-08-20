"""用于定义agent能力"""

from pydantic_ai import Agent
from pydantic_ai_harness import Shell

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

cap_agent = Agent(get_model(), capabilities=[Shell(cwd="./",
    denied_commands=[
        "rm",
        "rmdir",
        "del",
        "erase",
        "format",
        "mkfs",
        "shutdown",
        "reboot",
        "poweroff",
        "dd",
    ],
    denied_operators=[
        ">",
        ">>",
        "|",
        "&&",
        "||",
    ],
)])


__all__ = ['cap_agent']
