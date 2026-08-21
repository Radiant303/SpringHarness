"""调试脚本：把 step12 应用的真实 ANSI 输出倒出来，检查背景色码。

用法:
    python ansi_dump.py

输出:
    - 每一行是否带背景色 SGR 码 (48;...)
    - 全屏输出里 "48;2;0;0;0"（不透明黑）出现次数
    - 透明区域应该完全不出现 48; 开头的背景码
"""

import asyncio
import io
import re

from rich.console import Console

from step12_final import KimiStyleChatApp

WIDTH, HEIGHT = 120, 40


async def main() -> None:
    app = KimiStyleChatApp()
    async with app.run_test(size=(WIDTH, HEIGHT)) as pilot:
        # 发一条消息，让画面包含：欢迎框 + 对话 + 状态栏 + 输入框
        await pilot.press(*"hello", "enter")
        await pilot.pause(delay=1.0)

        strips = app.screen._compositor.render_strips()

    console = Console(
        width=WIDTH,
        height=HEIGHT,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )

    lines_with_bg = 0
    black_bg_count = 0
    default_bg_count = 0
    report_lines = []
    for y, strip in enumerate(strips):
        ansi = strip.render(console)
        # 匹配所有背景色码: 48;2;r;g;b 或 48;5;n
        bg_codes = re.findall(r"48;[25];[0-9;]*", ansi)
        black_bg_count += ansi.count("48;2;0;0;0")
        default_bg_count += ansi.count("\x1b[49m") + ansi.count(";49")
        if bg_codes:
            lines_with_bg += 1
            # 只保留可打印文本部分，方便看是哪一行
            text = re.sub(r"\x1b\[[0-9;]*m", "", ansi).rstrip()
            report_lines.append(f"  line {y:2}: bg={set(bg_codes)}  text={text[:60]!r}")

    print(f"总行数: {len(strips)}")
    print(f"带背景色码的行数: {lines_with_bg}")
    print(f"'48;2;0;0;0'(不透明黑) 出现次数: {black_bg_count}  (期望: 0)")
    print(f"'49'(终端默认背景) 出现次数: {default_bg_count}  (期望: >0，说明透明生效)")
    if report_lines:
        print("带背景的行明细:")
        print("\n".join(report_lines[:30]))


if __name__ == "__main__":
    asyncio.run(main())
