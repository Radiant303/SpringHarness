import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic_ai import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.messages import ModelMessagesTypeAdapter

SESSIONS_ROOT = Path.home() / ".springharness" / "sessions"
INDEX_FILE = SESSIONS_ROOT / "session_index.jsonl"


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
        self._update_index(messages)

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
        """索引为主：title 取自 session_index.jsonl，免读全量消息；
        索引未收录的文件读 meta 行兜底并现算 title。"""
        index = cls._read_index()
        result = []
        for path in sorted(SESSIONS_ROOT.rglob("rollout-*.jsonl")):
            entry = index.get(path.stem)
            if entry is not None:
                if entry.get("workspace") == str(workspace):
                    result.append((cls(path), entry))
                continue
            meta = cls._read_meta(path)
            if meta is None or meta.get("workspace") != str(workspace):
                continue
            meta["title"] = _session_title(cls(path))
            result.append((cls(path), meta))
        return result


    def _update_index(self, messages: list[ModelMessage]) -> None:
        """每轮写一条索引记录：title 只在首次出现用户消息时产生，之后沿用旧值。"""
        meta = self._read_meta(self.path) or {}
        old = self._read_index().get(self.path.stem) or {}
        record = {
            "id": self.path.stem,
            "workspace": meta.get("workspace"),
            "created_at": meta.get("created_at"),
            "title": old.get("title") or _first_user_text(messages),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with INDEX_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_index() -> dict[str, dict]:
        """读索引：同一 id 多条记录，后写覆盖先写；坏行只丢那一条更新。"""
        entries: dict[str, dict] = {}
        if not INDEX_FILE.exists():
            return entries
        for line in INDEX_FILE.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                entries[record["id"]] = record
        return entries

    @staticmethod
    def _read_meta(path: Path) -> dict | None:
        """读 session 文件首行 meta；首行不是 meta 对象（残缺/畸形文件）返回 None。"""
        try:
            with path.open(encoding="utf-8") as f:
                first = f.readline()
            meta = json.loads(first)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(meta, dict) or meta.get("type") != "meta":
            return None
        return meta


def _first_user_text(messages: list[ModelMessage], limit: int = 30) -> str | None:
    """第一条用户消息的截断文本；没有用户消息返回 None。"""
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    text = part.content.replace("\n", " ")
                    return text[:limit] + ("…" if len(text) > limit else "")
    return None


def _session_title(store: SessionStore, limit: int = 30) -> str:
    """会话标题 = 第一条用户消息截断。只用于索引未收录的老文件兜底。"""
    return _first_user_text(store.load_messages(), limit) or "(空会话)"


LOCAL_TZ = timezone(timedelta(hours=8))  # 展示层统一 +8


def format_local_time(iso: str) -> str:
    """UTC ISO 时间戳 → +8 的 'MM-dd HH:mm'；解析失败原样返回前 10 位。

    存储一律 UTC（created_at/updated_at），时区只是展示层的事。
    """
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # 无 tzinfo 的历史数据按 UTC 对待
    return dt.astimezone(LOCAL_TZ).strftime("%m-%d %H:%M")
