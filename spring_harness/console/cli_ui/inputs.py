"""输入相关组件：命令历史输入框 + 斜杠命令下拉框。

HistoryInput 已升级为多行 TextArea（粘贴折叠 / 高度自适应），
不再是 step12_final.py 的单行 Input。
"""

from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TextArea


class CommandDropdown(Vertical):
    """命令下拉框，出现在输入框上方。"""

    DEFAULT_CSS = """
    CommandDropdown {
        width: 1fr;
        height: auto;
        max-height: 8;
        background: transparent;
        border: round #4a9eff;
        margin: 0 1;
        display: none;
    }
    CommandDropdown .command-option {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    CommandDropdown .command-name {
        width: 20;
        color: #4a9eff;
    }
    CommandDropdown .command-desc {
        width: 1fr;
        color: ansi_bright_black;
    }
    CommandDropdown .selected .command-name {
        color: #ffffff;
        text-style: bold;
    }
    CommandDropdown .dropdown-count {
        width: 1fr;
        color: ansi_bright_black;
        padding: 0 1;
    }
    """

    def __init__(self, commands: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._commands: list[tuple[str, str]] = commands
        self._filtered: list[tuple[str, str]] = self._commands
        self._selected_index = 0
        self._rendered_names: list[str] = []
        self.visible = False

    def compose(self) -> ComposeResult:
        return []

    async def show(self) -> None:
        self.visible = True
        self.display = True
        await self._render_list()

    def hide(self) -> None:
        self.visible = False
        self.display = False

    def filter(self, query: str) -> None:
        """根据输入过滤命令。"""
        if not query.startswith("/"):
            self.hide()
            return
        query = query[1:].lower()
        self._filtered = [
            (name, desc)
            for name, desc in self._commands
            if name.startswith(query)
        ]
        self._selected_index = 0
        if self._filtered:
            self.app.run_worker(self.show())
        else:
            self.hide()

    async def _render_list(self) -> None:
        """重新渲染命令列表。列表内容没变时只更新选中态，避免销毁重建导致闪烁。"""
        names = [name for name, _ in self._filtered[:5]]
        if names == self._rendered_names and self.children:
            self._update_selection()
            return
        await self.remove_children()
        rows: list[Widget] = [
            HorizontalGroup(
                Static(
                    f"{'→ ' if idx == self._selected_index else '  '}{name}",
                    classes="command-name",
                ),
                Static(desc, classes="command-desc"),
                classes="command-option selected" if idx == self._selected_index else "command-option",
            )
            for idx, (name, desc) in enumerate(self._filtered[:5])
        ]
        rows.append(
            Static(f"  ({len(self._filtered)}/{len(self._commands)})", classes="dropdown-count")
        )
        await self.mount_all(rows)
        self._rendered_names = names

    def _update_selection(self) -> None:
        """只更新选中行的样式和箭头，不重建组件（避免闪烁）。"""
        for idx, row in enumerate(self.query(".command-option")):
            selected = idx == self._selected_index
            row.set_class(selected, "selected")
            name = self._filtered[idx][0]
            arrow = "→ " if selected else "  "
            row.query_one(".command-name", Static).update(f"{arrow}{name}")

    def move_up(self) -> None:
        if self._selected_index > 0:
            self._selected_index -= 1
            self._update_selection()

    def move_down(self) -> None:
        if self._selected_index < len(self._filtered) - 1:
            self._selected_index += 1
            self._update_selection()

    def select_current(self) -> str | None:
        """返回当前选中的命令。"""
        if 0 <= self._selected_index < len(self._filtered):
            return self._filtered[self._selected_index][0]
        return None


_LINE_BOUNDARIES = "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def _normalize_newlines(text: str) -> str:
    """把各种换行符统一为 ``\\n``，并保留原文末尾是否带换行。

    终端 bracketed paste 的换行可能是裸 ``\\r``（Windows Terminal 的惯例），
    而 Rich Content / TextArea 只认 ``\\n`` —— 不归一化的话，多行内容显示时
    会整段挤成一行。``splitlines`` 认识全部换行符（\\r\\n、裸 \\r、\\v、\\f、
    \\x1c-\\x1e、\\x85、\\u2028/\\u2029），借它做全覆盖归一化。
    """
    if not text:
        return text
    normalized = "\n".join(text.splitlines())
    if text[-1] in _LINE_BOUNDARIES:
        normalized += "\n"
    return normalized


class HistoryInput(TextArea):
    """多行输入框：Enter 提交、Shift+Enter/Ctrl+J 换行、↑↓ 翻历史、命令下拉导航。

    长粘贴折叠：粘贴超过 PASTE_PLACEHOLDER_THRESHOLD 字符的内容时不直接展开，
    只插入 ``[paste #N +M lines]`` / ``[paste #N C chars]`` 占位符（原文存
    ``_pastes``），提交时由 expand_pastes() 还原 —— 聊天区和模型都拿到完整
    内容；占位符版本只留在输入框和历史里，↑ 翻回来时仍是紧凑形态。
    """

    PASTE_PLACEHOLDER_THRESHOLD = 800

    class Submitted(Message):
        """Enter 提交。value 是输入框原始文本（占位符未展开）。"""

        def __init__(self, input: "HistoryInput", value: str) -> None:
            self.input = input
            self.value = value
            super().__init__()

        @property
        def control(self) -> "HistoryInput":
            return self.input

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.show_line_numbers = False
        self._history: list[str] = []
        self._history_pos: int | None = None
        self._draft: str = ""
        self._pastes: dict[str, str] = {}  # 占位符 → 粘贴原文
        self._paste_seq = 0

    # ---- 粘贴折叠 ----

    async def _on_paste(self, event: events.Paste) -> None:
        # 终端 bracketed paste。Textual 会沿 MRO 依次调用各级 _on_paste，
        # 必须 prevent_default 才能阻断 TextArea 默认的全文插入
        event.prevent_default()
        event.stop()
        if event.text:
            self._insert_clipboard(event.text)

    def action_paste(self) -> None:
        # ctrl+v 走 app.clipboard，和 bracketed paste 同一套折叠逻辑
        self._insert_clipboard(self.app.clipboard)

    def _insert_clipboard(self, text: str) -> None:
        # 先归一化换行：裸 \r 的粘贴直接进 TextArea / 聊天区都会丢换行
        text = _normalize_newlines(text)
        if len(text) > self.PASTE_PLACEHOLDER_THRESHOLD:
            self._paste_seq += 1
            n_lines = len(text.splitlines())
            placeholder = (
                f"[paste #{self._paste_seq} +{n_lines} lines]"
                if n_lines > 1
                else f"[paste #{self._paste_seq} {len(text)} chars]"
            )
            self._pastes[placeholder] = text
            text = placeholder
        self.replace(text, *self.selection)

    def expand_pastes(self, text: str) -> str:
        """提交时把占位符还原成粘贴原文；被用户改残的占位符原样保留。"""
        for placeholder, content in self._pastes.items():
            text = text.replace(placeholder, content)
        return text

    # ---- undo/redo ----

    def undo(self) -> None:
        # 规避 Textual 时序 bug：_undo_batch 先回滚文本并 _refresh_size，
        # 最后才由 edit.after 恢复选区——中途光标还停在旧位置，撤销多行编辑
        # 后光标落在越界行，scroll_cursor_visible 抛 ValueError 崩溃。
        # 提前把光标挪到 (0,0)（任何文档都合法），正确选区由 edit.after 恢复。
        self.move_cursor((0, 0))
        super().undo()

    def redo(self) -> None:
        # 同 undo()
        self.move_cursor((0, 0))
        super().redo()

    # ---- 键盘 ----

    async def _on_key(self, event: events.Key) -> None:
        # 所有需要"压住 TextArea 默认行为/绑定"的键都在这里拦（_on_key 先于绑定处理）
        dropdown = self.app.query_one("#command-dropdown", CommandDropdown)

        if dropdown.visible:
            if event.key == "up":
                event.stop()
                dropdown.move_up()
                return
            if event.key == "down":
                event.stop()
                dropdown.move_down()
                return
            if event.key == "enter":
                event.stop()
                event.prevent_default()  # 阻断 TextArea 默认的 enter 换行
                selected = dropdown.select_current()
                if selected is not None:
                    self.text = f"/{selected}"
                    dropdown.hide()
                    self.post_message(self.Submitted(self, self.text))
                return
            if event.key == "escape":
                event.stop()
                dropdown.hide()
                return

        # TextArea 默认 enter 换行；改为 enter 提交，Shift+Enter / Ctrl+J 换行
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self, self.text))
            return
        if event.key in ("shift+enter", "ctrl+j"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return

        # ↑↓：光标在首行 / 末行时翻历史，否则留给 TextArea 正常移动光标
        if event.key == "up" and self.cursor_location[0] == 0:
            event.stop()
            self._history_previous()
            return
        if event.key == "down" and self.cursor_at_last_line:
            event.stop()
            self._history_next()
            return
        if event.key not in ("up", "down"):
            self._history_pos = None

        await super()._on_key(event)

    def _history_previous(self) -> None:
        if not self._history:
            return
        if self._history_pos is None:
            self._draft = self.text
            self._history_pos = len(self._history) - 1
        elif self._history_pos > 0:
            self._history_pos -= 1
        self.text = self._history[self._history_pos]
        self.move_cursor(self.document.end)

    def _history_next(self) -> None:
        if self._history_pos is None:
            return
        self._history_pos += 1
        if self._history_pos >= len(self._history):
            self._history_pos = None
            self.text = self._draft
        else:
            self.text = self._history[self._history_pos]
        self.move_cursor(self.document.end)

    def push_history(self, text: str) -> None:
        if text:
            self._history.append(text)
        self._history_pos = None
        self._draft = ""
