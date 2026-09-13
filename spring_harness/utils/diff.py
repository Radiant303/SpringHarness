import difflib
import json


def make_diff(tool_name: str, args: object) -> str | None:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None
    if not isinstance(args, dict):
        return None
    path = str(args.get("path", ""))
    if tool_name == "edit_file":
        old, new = args.get("old_text"), args.get("new_text")
        if isinstance(old, str) and isinstance(new, str):
            return "".join(difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}", tofile=f"b/{path}",
            ))
    elif tool_name == "write_file":
        content = args.get("content")
        if isinstance(content, str):
            return "".join(difflib.unified_diff(
                [], content.splitlines(keepends=True),
                fromfile="/dev/null", tofile=f"b/{path}",
            ))
    elif tool_name == "edit_knowledge":
        diff = args.get("diff")
        if isinstance(diff, str):
            return diff
    return None
