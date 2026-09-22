from pydantic_ai.toolsets import ApprovalRequiredToolset
from pydantic_ai_harness import FileSystem


def filesystem(root_dir: str, read_only: bool = False):
    fs = FileSystem(root_dir=root_dir, read_only=read_only).get_toolset()

    return ApprovalRequiredToolset(
        fs,
        approval_required_func=lambda ctx, tool, args:
            tool.name in {

            },
    )
