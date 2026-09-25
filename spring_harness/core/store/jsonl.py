from __future__ import annotations

import datetime
import json
import uuid
from datetime import timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from pydantic_ai import ModelMessage
from pydantic_ai.messages import ModelMessagesTypeAdapter

from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.log import logger
from spring_harness.core.store.paging import (
    dedup_segments,
    first_user_text,
    page_history,
)

# 兼容既有导入路径：_first_user_text 的逻辑已上收到 store/paging.py
_first_user_text = first_user_text

SESSIONS_ROOT = Path.home() / ".springharness" / "sessions"
INDEX_FILE = SESSIONS_ROOT / "session_index.jsonl"


class JsonlSessionStore:
    """一个 session 一个 JSONL 文件：首行 meta，之后每行一条 ModelMessage。
    历史被改写（压缩/合并）时插入一行 history_rewrite 标记，其后为新基线；
    文件只追加，永不覆盖。"""

    def __init__(self, path: Path, pending_meta: dict | None = None):
        self.path = path
        self._pending_meta = pending_meta

    @property
    def session_id(self) -> str:
        return self.path.stem

    @classmethod
    def create(cls, workspace: Path) -> JsonlSessionStore:
        now = datetime.datetime.now(datetime.UTC)
        # 日期分片目录 + 文件名带时间戳和 uuid，字典序即时间序
        stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
        path = SESSIONS_ROOT / now.strftime("%Y/%m/%d") / f"rollout-{stamp}-{uuid.uuid4()}.jsonl"
        meta = {
            "type": "meta",
            "id": path.stem,
            "workspace": str(workspace),
            "created_at": now.isoformat(),
        }
        return cls(path, pending_meta=meta)

    @staticmethod
    def _dump_line(msg: ModelMessage) -> str:
        # ModelMessagesTypeAdapter 是 list 的适配器，包一层单元素列表
        return ModelMessagesTypeAdapter.dump_json([msg]).decode()

    def _ensure_file(self) -> None:
        """首次写入时创建文件并落 meta 行。"""
        if self._pending_meta is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._pending_meta, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self._pending_meta = None

    def append(self, messages: list[ModelMessage]) -> None:
        """每轮结束（含异常终止）后调用，追加增量。"""
        self._ensure_file()
        with self.path.open("a", encoding="utf-8") as f:
            for msg in messages:
                f.write(self._dump_line(msg) + "\n")
        self._update_index(messages)

    def append_rewritten(self, messages: list[ModelMessage]) -> None:
        """历史被压缩/消息合并改写时调用：先追加一条 history_rewrite 标记，
        再把新基线整体追加到文件末尾——旧内容留在文件里备查，保住追加原则。"""
        marker = {
            "type": "history_rewrite",
            "at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        self._ensure_file()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(marker, ensure_ascii=False) + "\n")
            for msg in messages:
                f.write(self._dump_line(msg) + "\n")
        self._update_index(messages)

    def _load_segments(self) -> list[list[ModelMessage]]:
        segments: list[list[ModelMessage]] = [[]]
        try:
            with self.path.open(encoding="utf-8-sig", errors="replace") as stream:
                for line_no, line in enumerate(stream, start=1):
                    line = line.lstrip("\ufeff \t\r\n")
                    if not line:
                        continue
                    try:
                        # 明确区分字典行（元数据 / 控制标记）与数组行（ModelMessage 列表）
                        if line.startswith("{"):
                            data = json.loads(line)
                            msg_type = data.get("type")
                            if msg_type == "meta":
                                continue
                            if msg_type == "history_rewrite":
                                segments.append([])
                                continue
                            logger.warning(
                                "会话文件 [%s:%d] 忽略未知类型的控制行 (type=%r)",
                                self.path.name,
                                line_no,
                                msg_type,
                            )
                            continue

                        if line.startswith("["):
                            segments[-1].extend(ModelMessagesTypeAdapter.validate_json(line))
                        else:
                            logger.warning(
                                "会话文件 [%s:%d] 非预期格式行（未以 { 或 [ 开头），跳过该行",
                                self.path.name,
                                line_no,
                            )
                    except (json.JSONDecodeError, ValidationError) as e:
                        logger.warning(
                            "会话文件 [%s:%d] 消息解析异常 (%s)，跳过该行: %s",
                            self.path.name,
                            line_no,
                            type(e).__name__,
                            e,
                        )
                        continue
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "会话文件 [%s:%d] 处理行发生未预期错误，跳过该行: %s",
                            self.path.name,
                            line_no,
                            e,
                        )
                        continue
        except OSError as e:
            logger.warning("会话文件 [%s] 打开/读取失败: %s", self.path.name, e)
        return segments

    def load_messages(self) -> list[ModelMessage]:
        """发给模型的当前历史：最后一段（history_rewrite 标记之后的新基线）。"""
        return self._load_segments()[-1]

    def load_display_segments(self) -> list[list[ModelMessage]]:
        return dedup_segments(self._load_segments())

    def load_for_resume(self) -> tuple[list[ModelMessage], list[list[ModelMessage]]]:
        """一次解析返回完整模型历史与去重分段。"""
        messages, page = self.query_history()
        return messages, page.segments

    def load_full(self) -> list[ModelMessage]:
        """返回按 rewrite/dedup 规则解析后的完整历史。"""
        return [m for seg in self.load_display_segments() for m in seg]

    def query_history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> tuple[list[ModelMessage], HistoryPage]:
        """一次解析返回当前完整模型历史与按消息数分页的历史快照。

        介质读取之后的分页语义（游标快照、去重、切片）在 store/paging.py 统一实现，
        与云端 MySQL 实现共用，保证游标格式与行为一致。
        """
        raw_segments = self._load_segments() if self.path.exists() else []
        return page_history(raw_segments, self.session_id, cursor, limit, direction)

    @classmethod
    def list_sessions(cls, workspace: Path) -> list[tuple[JsonlSessionStore, dict]]:
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
            store = cls(path)
            messages = store.load_messages()
            if not messages:
                continue
            meta["title"] = first_user_text(messages) or "(空会话)"
            result.append((store, meta))
        return result


    def _update_index(self, messages: list[ModelMessage]) -> None:
        """每轮写一条索引记录：title 只在首次出现用户消息时产生，之后沿用旧值。"""
        meta = self._read_meta(self.path) or {}
        old = self._read_index().get(self.path.stem) or {}
        record = {
            "id": self.path.stem,
            "workspace": meta.get("workspace"),
            "created_at": meta.get("created_at"),
            "title": old.get("title") or first_user_text(messages),
            "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
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
            with path.open(encoding="utf-8-sig", errors="replace") as f:
                first = f.readline().lstrip("\ufeff \t\r\n")
            meta = json.loads(first)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(meta, dict) or meta.get("type") != "meta":
            return None
        return meta


LOCAL_TZ = timezone(timedelta(hours=8))  # 展示层统一 +8


def format_local_time(iso: str) -> str:
    """UTC ISO 时间戳 → +8 的 'MM-dd HH:mm'；解析失败原样返回前 10 位。
    """
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return iso[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(LOCAL_TZ).strftime("%m-%d %H:%M")
