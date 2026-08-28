import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.messages import ModelMessagesTypeAdapter

SESSIONS_ROOT = Path.home() / ".springharness" / "sessions"


class SessionStore:
    """一个 session 一个 JSONL 文件：首行 meta，之后每行一条 ModelMessage。"""

    def __init__(self, path: Path):
        self.path = path

    @classmethod
    def create(cls, workspace: Path) -> "SessionStore":
        now = datetime.now()
        # 日期分片目录 + 文件名带时间戳和 uuid，字典序即时间序
        day_dir = SESSIONS_ROOT / now.strftime("%Y/%m/%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
        path = day_dir / f"rollout-{stamp}-{uuid.uuid4()}.jsonl"
        meta = {
            "type": "meta",
            "id": path.stem,
            "workspace": str(workspace),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")
        return cls(path)

    def append(self, messages: list[ModelMessage]) -> None:
        """每轮结束后调用，追加增量。append 单行天然原子，不需要 tmp+rename。"""
        with self.path.open("a", encoding="utf-8") as f:
            for msg in messages:
                # ModelMessagesTypeAdapter 是 list 的适配器，包一层单元素列表
                line = ModelMessagesTypeAdapter.dump_json([msg]).decode()
                f.write(line + "\n")

    def load_messages(self) -> list[ModelMessage]:
        """逐行读、逐条校验；尾部坏行截断，保住前面完好的部分。"""
        messages: list[ModelMessage] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict) and data.get("type") == "meta":
                    continue
                messages.extend(ModelMessagesTypeAdapter.validate_json(line))
            except Exception:
                break
        return messages

    @classmethod
    def list_sessions(cls, workspace: Path) -> list[tuple["SessionStore", dict]]:
        """列表 = 扫目录读各文件首行 meta，按 workspace 过滤。免索引。"""
        result = []
        for path in sorted(SESSIONS_ROOT.rglob("rollout-*.jsonl")):
            with path.open(encoding="utf-8") as f:
                first = f.readline()
            try:
                meta = json.loads(first)
            except json.JSONDecodeError:
                continue
            if not isinstance(meta, dict) or meta.get("type") != "meta":
                continue
            if meta.get("workspace") != str(workspace):
                continue
            result.append((cls(path), meta))

        return result


def _session_title(store: SessionStore, limit: int = 30) -> str:
    """会话标题 = 第一条用户消息截断，用于 /resume 列表。"""
    for msg in store.load_messages():
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    text = part.content.replace("\n", " ")
                    return text[:limit] + ("…" if len(text) > limit else "")
    return "(空会话)"
