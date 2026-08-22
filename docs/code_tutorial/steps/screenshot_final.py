"""生成 step12 成品的 SVG 截图，用于检查样式。

运行：python screenshot_final.py
输出：final_chat.svg / final_dropdown.svg / final_model.svg

注意：Textual/Rich 的终端列宽和 SVG 的字符数不是一回事。CJK 字符在
终端里占两列，但 Rich 默认按一个字符计算 SVG 的 ``textLength``，所以
截图里中英文分段之间会出现异常空白。这里仅修正导出文件，不改运行时布局。
"""
import asyncio
import html
import re

from rich.cells import cell_len

from .step12_final import KimiStyleChatApp

_TEXT_NODE_RE = re.compile(
    r'(<text\b[^>]*\btextLength=")([0-9.]+)("[^>]*>)(.*?)(</text>)',
    re.DOTALL,
)
_SYMBOL_CHARS = frozenset("✨●→╭─╮│╰╯▪◆")


def _fix_svg_text_metrics(svg: str) -> str:
    """让 SVG 的每个文本片段和终端列位置保持一致。

    Rich 的 SVG 导出用 ``len(text)`` 计算 ``textLength``，但终端布局用
    ``cell_len(text)``。中文、全角标点和 emoji 因而会让后续片段错位。
    这里沿用 Rich 已写入的字符宽度，只把字符数换成终端 cell 数。
    """

    def replace(match: re.Match[str]) -> str:
        prefix, old_length, suffix, body, closing = match.groups()
        plain = html.unescape(body)
        if not plain or "\\n" in plain:
            return match.group(0)
        old_length_value = float(old_length)
        character_count = len(plain)
        if character_count == 0:
            return match.group(0)
        char_width = old_length_value / character_count
        new_length = char_width * cell_len(plain)
        if any(char in _SYMBOL_CHARS for char in plain):
            suffix = suffix[:-1] + ' font-family="Segoe UI Symbol">'
        return f"{prefix}{new_length:g}{suffix}{body}{closing}"

    return _TEXT_NODE_RE.sub(replace, svg)


def _prepare_svg(svg: str) -> str:
    """应用 Windows 中文字体和 CJK 终端宽度修正。"""
    # 这里替换的是导出 SVG 的 CSS，不影响 Textual/Rich 的实际渲染。
    svg = re.sub(
        r"font-family: Fira Code, monospace;",
        'font-family: "Noto Sans SC", "Microsoft YaHei", "DengXian", "SimSun", "Segoe UI Emoji", "Segoe UI Symbol", monospace;',
        svg,
    )
    svg = svg.replace(
        "font-variant-east-asian: full-width;",
        "font-variant-east-asian: proportional-width;",
    )
    return _fix_svg_text_metrics(svg)


async def main() -> None:
    app = KimiStyleChatApp()
    async with app.run_test(size=(120, 35)) as pilot:  # pyright: ignore[reportUnknownVariableType]
        inp = app.query_one("#user-input")
        inp.focus()

        # 连发三条消息，检查多条之间的间距
        for text in ["你好", "csaca", "再试一次"]:
            await pilot.press(*list(text), "enter")
            await pilot.pause(3)

        # 截图 1：聊天界面
        svg = _prepare_svg(app.export_screenshot())
        with open("final_chat.svg", "w", encoding="utf-8") as f:
            f.write(svg)

        # 打开命令下拉
        await pilot.press("/")
        await pilot.pause(0.5)
        svg = _prepare_svg(app.export_screenshot())
        with open("final_dropdown.svg", "w", encoding="utf-8") as f:
            f.write(svg)

        # 打开 model 弹窗
        await pilot.press(*list("model"), "enter")
        await pilot.pause(0.5)
        svg = _prepare_svg(app.export_screenshot())
        with open("final_model.svg", "w", encoding="utf-8") as f:
            f.write(svg)

        print("截图已生成: final_chat.svg / final_dropdown.svg / final_model.svg")


if __name__ == "__main__":
    asyncio.run(main())
