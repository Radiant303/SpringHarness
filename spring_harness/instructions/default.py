from pathlib import Path

from pydantic_ai import Agent, DeferredToolRequests, RunContext

from spring_harness.core.agent.deps import CodingAgentDeps


def register_default_instructions(
    agent: Agent[CodingAgentDeps, DeferredToolRequests | str]
):
    @agent.instructions
    async def set_workspace(ctx: RunContext[CodingAgentDeps]) -> str:
        return f"Your working directory is {ctx.deps.workspace}; you must only read, write, and operate on files within this directory and cannot access anything outside it."

    # 与 capabilities/code_mode.py 的配置对应（tools=['read_file', 'search_files']，
    # /work=overlay、/scratch=读写）。配置变更时这段指令需同步修改，否则会误导模型。
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
            "module, no `dir()`. "
            "The workspace is mounted at `/work` as an OVERLAY: reads see the real files, "
            "but writes are discarded when the snippet ends — never store anything a later "
            "step needs under `/work`. For intermediate artifacts that must persist across "
            "`run_code` calls (generated data, downloaded content, temp outputs, draft "
            "analysis), write under `/scratch`, a read-write mount persisted to "
            "`.agent-scratch/` in the workspace. Final deliverables belong in the workspace "
            "via the `write_file`/`edit_file` tools (which require user approval), never in "
            "`/scratch`. Environment variables and the clock are unavailable. State persists "
            "between `run_code` calls (REPL-style)."
        )
