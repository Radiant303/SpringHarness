"""输入相关组件：命令历史输入框 + 斜杠命令下拉框。

代码从 step12_final.py 提炼，行为一致；CommandDropdown 的命令列表
从模块常量改成了构造参数。
"""

from textual import events
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Vertical
from textual.widgets import Input, Static


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
        color: #7a8391;
    }
    CommandDropdown .selected .command-name {
        color: #ffffff;
        text-style: bold;
    }
    CommandDropdown .dropdown-count {
        width: 1fr;
        color: #7a8391;
        padding: 0 1;
    }
    """

    def __init__(self, commands: list[tuple[str, str]], **kwargs) -> None:
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
        rows = [
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


class HistoryInput(Input):
    """带上下历史记忆的输入框，也负责命令下拉的键盘导航。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_pos: int | None = None
        self._draft: str = ""

    async def on_key(self, event: events.Key) -> None:
        dropdown = self.app.query_one("#command-dropdown", CommandDropdown)

        if dropdown.visible:
            if event.key == "up":
                event.stop()
                dropdown.move_up()
                return
            elif event.key == "down":
                event.stop()
                dropdown.move_down()
                return
            elif event.key == "enter":
                event.stop()
                selected = dropdown.select_current()
                if selected is not None:
                    self.value = f"/{selected}"
                    dropdown.hide()
                    # 立即触发提交
                    self.post_message(Input.Submitted(self, self.value))
                return
            elif event.key == "escape":
                event.stop()
                dropdown.hide()
                return

        if event.key == "up":
            event.stop()
            self._history_previous()
        elif event.key == "down":
            event.stop()
            self._history_next()
        else:
            self._history_pos = None

    def _history_previous(self) -> None:
        if not self._history:
            return
        if self._history_pos is None:
            self._draft = self.value
            self._history_pos = len(self._history) - 1
        elif self._history_pos > 0:
            self._history_pos -= 1
        self.value = self._history[self._history_pos]

    def _history_next(self) -> None:
        if self._history_pos is None:
            return
        self._history_pos += 1
        if self._history_pos >= len(self._history):
            self._history_pos = None
            self.value = self._draft
        else:
            self.value = self._history[self._history_pos]

    def push_history(self, text: str) -> None:
        if text:
            self._history.append(text)
        self._history_pos = None
        self._draft = ""
