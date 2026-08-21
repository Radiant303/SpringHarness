"""第 13 步：用 cli_ui SDK 做一个 agent（不再自己造界面）。

学到什么：
- 前 12 步教你一个零件一个零件地造出成品界面（step12_final.py 有 749 行）；
  这一步把同一份 UI 封装成 `cli_ui` 包，你只写「业务逻辑」——本文件几十行
  就得到和 step12 一模一样的界面。
- 子类化 CliApp，实现 handle_input()：start_assistant() 开一条 AI 消息，
  write_thinking / write_answer 流式累加，show_tool_call 显示工具调用。

和第 12 步的区别：不教原理，教怎么用。想改界面本身，回去读第 1-12 章。

运行：python steps/step13_sdk.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 让 cli_ui 可被 import

from cli_ui import CliApp


async def stream(write, text, delay=0.03, chunk=4):
    """把 text 按小块流式写给 write（write_thinking / write_answer）。"""
    for i in range(0, len(text), chunk):
        await write(text[i : i + chunk])
        await asyncio.sleep(delay)


class FakeAgent(CliApp):
    """一个假装会读文件、跑命令的 agent。"""

    async def handle_input(self, text: str) -> None:
        assistant = await self.start_assistant()
        await stream(assistant.write_thinking, f"用户问「{text}」，先看看项目里有什么……")

        await self.show_tool_call(
            "Read", "README.md",
            result="# 用 Textual 做 Claude Code 风格终端渲染\n\n本目录包含递增示例……",
        )
        await self.show_tool_call(
            "Bash", "ls steps/",
            result="\n".join(f"step{i:02d}_xxx.py" for i in range(1, 8)) + "\n...(略)",
        )

        await stream(assistant.write_answer, (
            f"你输入的是 **{text}**。\n\n"
            "这是一个 `cli_ui` SDK 的演示：\n"
            "- thinking、工具调用、Markdown 回答都是 `await` 一行搞定\n"
            "- 界面和第 12 步的成品完全相同（主题 / 历史 / 下拉框 / /model）"
        ))
        await assistant.finish()
        self.set_status(context="context: 1% (2.6k/256k)")

    async def handle_command(self, command: str) -> None:
        await self.show_system(f"演示版没有实现 /{command}（/model 是内置的）")


if __name__ == "__main__":
    FakeAgent(
        title="cli_ui Demo",
        model="K3-256k",
        version="0.1.0",
        commands=[("clear", "Clear chat history"), ("about", "About this demo")],
    ).run()
