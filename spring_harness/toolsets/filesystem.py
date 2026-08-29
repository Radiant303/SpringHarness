from pydantic_ai.toolsets import ApprovalRequiredToolset
from pydantic_ai_harness import FileSystem


def filesystem(root_dir: str):
    fs = FileSystem(root_dir=root_dir).get_toolset()

    return ApprovalRequiredToolset(
        fs,
        approval_required_func=lambda ctx, tool, args:
            tool.name in {
                "edit_file",
                "write_file",
            },
    )
