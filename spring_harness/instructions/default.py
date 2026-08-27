from pathlib import Path

from pydantic_ai import Agent, DeferredToolRequests, RunContext

from spring_harness.core.agent.deps import CodingAgentDeps


def register_default_instructions(
    agent: Agent[CodingAgentDeps, DeferredToolRequests | str]
):
    @agent.instructions
    async def set_workspace(ctx: RunContext[CodingAgentDeps]) -> str:
        return f"Your working directory is {ctx.deps.workspace}; you must only read, write, and operate on files within this directory and cannot access anything outside it."

    # 与 agent.py 中的 CodeMode 配置对应（tools=['read_file', 'search_files']，
    # mount=/work 读写）。若移除 CodeMode，这段指令需同步删除，否则会误导模型。
    @agent.instructions
    async def code_mode_rules(ctx: RunContext[CodingAgentDeps]) -> str:
        return (
            "Code mode rules. TWO NAMESPACES — do not confuse them. "
            "Top-level tools (call directly): `list_directory`, `write_file`, `edit_file`, "
            "`find_files`, `create_directory`, `file_info`, `run_code` and others. "
            "Sandbox functions: `read_file` and `search_files` are NOT top-level tools — "
            "their signatures appear only in the `run_code` description because they are "
            "callable exclusively as async functions inside `run_code` code. Before emitting "
            "any tool call, check the name against the top-level tool list: `read_file` and "
            "`search_files` are absent from it on purpose, and calling them directly fails "
            "with 'Unknown tool name'. To read a file or search, call `run_code` with code "
            "like `content = await read_file(path='a.py')`, ending with a bare expression "
            "that returns what you need. "
            "The sandbox runs Monty, a Python subset: only `sys`, `typing`, `asyncio`, "
            "`math`, `json`, `re`, `unicodedata`, `datetime`, `os`, `pathlib` can be "
            "imported, and their APIs are trimmed — no `os.walk`/`os.getcwd`, no "
            "`Path.rglob`/`Path.glob`, `Path.read_text()` takes no arguments, no `glob` "
            "module, no `dir()`. The workspace is mounted at `/work` (read-write), so "
            "`pathlib` I/O works only under `/work`; environment variables and the clock "
            "are unavailable. State persists between `run_code` calls (REPL-style)."
        )
