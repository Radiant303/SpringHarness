"""极细竖滚动条渲染器。

Textual 自带的竖滚动条是「整格反显的实心块」（scrollbar.py 里 body 用
``" " * thickness`` + ``reverse=True``），所以哪怕把 scrollbar-size 压到 1，
它也是满满一整列纯色，跟终端原生滚动条一样粗。

这里换成用 1/8 块字符（▏）当**前景色**画，轨道不填色：
一列里只剩一条靠左的细线，观感接近 GUI 的细滚动条。

只给单个滚动容器换上，不动全局（输入框等其它滚动条保持原样）::

    self.vertical_scrollbar.renderer = ThinScrollBarRender

``ScrollBar.renderer`` 是官方留的扩展点，见 textual/scrollbar.py 中
``ScrollBar.renderer`` 的类注释。
"""

from __future__ import annotations

from math import ceil
from typing import ClassVar

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBarRender


class ThinScrollBarRender(ScrollBarRender):
    """只画一条细竖线的滚动条渲染器（竖向专用，横向回退库实现）。"""

    # 由细到粗的备选取值，改一个常量就能换观感：
    #   "│" U+2502  细线（居中，等宽字体里最稳，但不到边缘）
    #   "▏" U+258F  1/8 块（默认，贴格子左边）
    #   "▎" U+258E  1/4 块
    #   "▌" U+258C  1/2 块
    #   "█" U+2588  整格（= 库默认观感）
    THUMB_GLYPH: ClassVar[str] = "▏"
    """滑块字符。"""
    TRACK_GLYPH: ClassVar[str] = " "
    """轨道字符（配合 CSS 里的透明背景，等于不画轨道）。"""

    @classmethod
    def render_bar(
        cls,
        size: int = 25,
        virtual_size: float = 50,
        window_size: float = 20,
        position: float = 0,
        thickness: int = 1,
        vertical: bool = True,
        back_color: Color = Color.parse("#555555"),
        bar_color: Color = Color.parse("bright_magenta"),
    ) -> Segments:
        if not vertical:
            # 横向保持库原样（本项目聊天区不显示横向条，走到这里也是兜底）
            return super().render_bar(
                size=size,
                virtual_size=virtual_size,
                window_size=window_size,
                position=position,
                thickness=thickness,
                vertical=vertical,
                back_color=back_color,
                bar_color=bar_color,
            )

        size = int(size)
        # meta 不能丢：点击轨道上/下半区翻页、按住滑块拖动，全靠它
        up_segment = Segment(
            cls.TRACK_GLYPH,
            Style(bgcolor=back_color, meta={"@mouse.down": "scroll_up"}),
        )
        down_segment = Segment(
            cls.TRACK_GLYPH,
            Style(bgcolor=back_color, meta={"@mouse.down": "scroll_down"}),
        )
        thumb_segment = Segment(
            cls.THUMB_GLYPH,
            Style(color=bar_color, meta={"@mouse.down": "grab"}),
        )
        segments = [up_segment] * size

        if window_size and size and virtual_size and virtual_size > size:
            thumb = max(1, min(size, ceil(size * window_size / virtual_size)))
            span = max(1.0, virtual_size - window_size)
            offset = min(max(position, 0.0), span)
            start = min(int(round((size - thumb) * offset / span)), size - thumb)
            start = max(0, start)
            segments[start : start + thumb] = [thumb_segment] * thumb
            segments[start + thumb :] = [down_segment] * (size - start - thumb)

        return Segments(segments, new_lines=True)
