"""CJK（中日韩）友好换行工具 —— 解决「中文长段落提前换行、右侧留大片空白」。

问题根源（不用改 Textual / Rich 源码也能绕过）：
- Textual 的文本换行最终走 Rich 的 divide_line()，它只认「空格分词」：
  一行里放下一个「词」才放得下，放不下就整体挪到下一行。
- 英文词短，这个策略没问题；但一段没有空格的中文会被当成「一个超长的词」。
- 这个词只要不是比整行还宽，Rich 就不会折断它，而是整段挪到下一行
  → 当前行只写了半行多就换行，右侧空出一大片。

本模块的做法：
- cjk_divide_line()：自己算断行位置 —— 优先在空白处断（和英文一样），
  CJK 宽字符之间随时可断（中文里任何两个汉字之间都允许换行），
  只有单个词比整行还宽时才硬折（和 Rich 的 fold 行为一致）。
- CJKContentVisual：一个 Visual 包装层。先按上面的规则把内容预断行
  （用 Content.divide 切开，样式 spans 原样保留），再交给原生渲染流程。
  这样高度计算（get_height）和实际绘制（render_strips）用的是同一份断行，
  不会出现「算的高度」和「画的高度」不一致。
- CJKMarkdown / CJKMarkdownParagraph：把 Markdown 里的段落块换成用
  CJKContentVisual 包装的版本。标题、列表、代码块等不受影响。
- CJKStatic：给普通 Static 使用同一套换行；适合用户消息、thinking、日志等。

用法：
    # Markdown 回答
    yield CJKMarkdown(id="answer-md")

    # 普通文本（用户消息 / thinking / 日志）
    yield CJKStatic("中文长文本")
"""

import unicodedata
from types import MappingProxyType
from typing import ClassVar

from rich.cells import chop_cells
from textual._cells import cell_len
from textual.content import Content
from textual.css.styles import RulesMap
from textual.strip import Strip
from textual.style import Style
from textual.visual import RenderOptions, Visual, VisualType
from textual.widgets import Markdown, Static
from textual.widgets._markdown import MarkdownBlock, MarkdownParagraph


def _is_wide(char: str) -> bool:
    """是不是占 2 格的宽字符（CJK 表意文字、全角标点等）。"""
    return unicodedata.east_asian_width(char) in ("W", "F")


def cjk_divide_line(text: str, width: int) -> list[int]:
    """计算一行（不含 \\n）文本的断行位置，返回字符偏移列表。

    规则：
    - 优先在空白处断行（和英文排版一样）；
    - CJK 宽字符之间随时可断（中文的习惯）；
    - 单个词比整行还宽时硬折（和 Rich 的 fold 一致）。
    """
    if width <= 0:
        return []
    offsets: list[int] = []
    cell_offset = 0  # 当前行已用格数
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            # 空白留在当前行尾（渲染时会被裁掉）；连空格都放不下就断在空白前
            if cell_offset >= width:
                offsets.append(index)
                cell_offset = 0
            else:
                cell_offset += 1
            index += 1
            continue
        # 取一个「词」：宽字符自己就是一个词；连续的非宽字符（拉丁词）整体算一个
        if _is_wide(char):
            end = index + 1
        else:
            end = index
            while end < len(text) and not text[end].isspace() and not _is_wide(text[end]):
                end += 1
        word = text[index:end]
        word_width = cell_len(word)
        if cell_offset and cell_offset + word_width > width:
            # 当前行放不下这个词 → 断在它前面
            offsets.append(index)
            cell_offset = 0
        # 词比整行还宽 → 硬折成多段
        while word_width > width:
            piece = chop_cells(word, width)[0]
            index += len(piece)
            offsets.append(index)
            word = text[index:end]
            word_width = cell_len(word)
        cell_offset += word_width
        index = end
    return offsets


class CJKContentVisual(Visual):
    """Visual 包装层：把内容按 CJK 友好规则预断行，再委托给原生 Content 渲染。"""

    def __init__(self, content: Content) -> None:
        self._content = content
        self._wrap_cache: dict[int, Content] = {}

    def __str__(self) -> str:
        """调试 / 测试时仍能用 str(widget.render()) 取得原始文本。"""
        return self._content.plain

    @property
    def plain(self) -> str:
        """兼容需要读取 .plain 的调用方。"""
        return self._content.plain

    def _wrapped(self, width: int) -> Content:
        """按 width 预断行（保留样式），结果按宽度缓存。"""
        if width not in self._wrap_cache:
            lines: list[Content] = []
            for line in self._content.split(allow_blank=True):
                offsets = cjk_divide_line(line.plain, width)
                lines.extend(line.divide(offsets) if offsets else [line])
            self._wrap_cache[width] = Content("\n").join(lines)
        return self._wrap_cache[width]

    def render_strips(
        self, width: int, height: int | None, style: Style, options: RenderOptions
    ) -> list[Strip]:
        line_pad = options.rules.get("line_pad", 0) * 2
        return self._wrapped(width - line_pad).render_strips(width, height, style, options)

    def get_height(self, rules: RulesMap, width: int) -> int:
        line_pad = rules.get("line_pad", 0) * 2
        return self._wrapped(width - line_pad).get_height(rules, width)

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        return self._content.get_optimal_width(rules, container_width)

    def get_minimal_width(self, rules: RulesMap) -> int:
        return self._content.get_minimal_width(rules)


class CJKStatic(Static):
    """普通文本组件：字符串 / Rich Text 都使用 CJK 友好换行。"""

    def render(self):
        visual = super().render()
        if isinstance(visual, Content):
            return CJKContentVisual(visual)
        return visual


class CJKMarkdownParagraph(MarkdownParagraph):
    """换行对 CJK 友好的 Markdown 段落。"""

    def update(self, content: VisualType = "", *, layout: bool = True) -> None:
        if isinstance(content, Content):
            content = CJKContentVisual(content)
        super().update(content, layout=layout)


class CJKMarkdown(Markdown):
    """段落使用 CJK 友好换行的 Markdown 组件（其它块类型不变）。"""

    BLOCKS: ClassVar[MappingProxyType[str, type[MarkdownBlock]]] = MappingProxyType({
        **Markdown.BLOCKS,
        "paragraph_open": CJKMarkdownParagraph,
    })
