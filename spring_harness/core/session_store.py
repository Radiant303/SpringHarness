from __future__ import annotations

import base64
import datetime
import json
import uuid
from datetime import timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from pydantic_ai import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.messages import ModelMessagesTypeAdapter

from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.hooks.model import is_file_monitor_message
from spring_harness.core.log import logger

SESSIONS_ROOT = Path.home() / ".springharness" / "sessions"
INDEX_FILE = SESSIONS_ROOT / "session_index.jsonl"


class SessionStore:
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
    def create(cls, workspace: Path) -> SessionStore:
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

    @staticmethod
    def _dedup_segments(segments: list[list[ModelMessage]]) -> list[list[ModelMessage]]:
        """跨段去重：压缩改写后的新基线与旧段尾部有重叠前缀时，剥掉重叠部分。"""
        result: list[list[ModelMessage]] = []
        acc: list[ModelMessage] = []
        for seg in segments:
            strip_lo = strip_hi = 0
            for s in range(min(3, len(seg)) + 1):
                for k in range(min(len(acc), len(seg) - s), 0, -1):
                    if acc[-k:] == seg[s:s + k]:
                        if s + k > strip_hi:
                            strip_lo, strip_hi = s, s + k
                        break
            deduped = [*seg[:strip_lo], *seg[strip_hi:]]
            result.append(deduped)
            acc.extend(deduped)
        return result

    def load_display_segments(self) -> list[list[ModelMessage]]:
        return self._dedup_segments(self._load_segments())

    def load_for_resume(self) -> tuple[list[ModelMessage], list[list[ModelMessage]]]:
        """一次解析返回完整模型历史与去重分段。"""
        messages, page = self.query_history()
        return messages, page.segments

    def load_full(self) -> list[ModelMessage]:
        """返回按 rewrite/dedup 规则解析后的完整历史。"""
        return [m for seg in self.load_display_segments() for m in seg]

    def _encode_cursor(self, segment_count: int, message_count: int, offset: int) -> str:
        payload = json.dumps([1, self.session_id, segment_count, message_count, offset], separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    def _decode_cursor(self, cursor: str) -> tuple[int, int, int]:
        try:
            payload = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError("invalid history cursor") from e
        if (
            not isinstance(data, list) or len(data) != 5
            or type(data[0]) is not int or data[0] != 1 or data[1] != self.session_id
            or any(type(value) is not int or value < 0 for value in data[2:])
        ):
            raise ValueError("invalid history cursor")
        return data[2], data[3], data[4]

    def query_history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> tuple[list[ModelMessage], HistoryPage]:
        """一次解析返回当前完整模型历史与按消息数分页的历史快照。

        游标编码版本、会话 ID、存储段数、原始消息数、去重后消息边界。
        存储前缀固定快照，后续追加和 rewrite 不改变既有分页；新查询用空游标。
        forward 包含边界后的消息，backward 包含边界前的消息，结果始终正序。
        limit=None 返回完整当前历史，此时不接受 cursor。
        """
        if direction not in {"forward", "backward"}:
            raise ValueError("invalid history direction")
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("invalid history limit")
        if cursor is not None and limit is None:
            raise ValueError("history cursor requires a limit")
        position = self._decode_cursor(cursor) if cursor is not None else None
        raw_segments = self._load_segments() if self.path.exists() else []
        messages = raw_segments[-1] if raw_segments else []
        segment_count = len(raw_segments)
        message_count = sum(map(len, raw_segments))
        snapshot = raw_segments
        if position is not None:
            segment_count, message_count, _ = position
            if segment_count > len(raw_segments):
                raise ValueError("history cursor snapshot is out of range")
            snapshot = raw_segments[:segment_count]
            preceding_count = sum(map(len, snapshot[:-1]))
            if not preceding_count <= message_count <= sum(map(len, snapshot)):
                raise ValueError("history cursor snapshot is out of range")
            if snapshot:
                snapshot[-1] = snapshot[-1][:message_count - preceding_count]
        segments = self._dedup_segments(snapshot)
        total = sum(map(len, segments))
        if limit is None:
            return messages, HistoryPage(
                segments=segments if total else [], first_segment_index=0 if total else None,
            )
        boundary = position[2] if position is not None else (total if direction == "backward" else 0)
        if boundary > total:
            raise ValueError("history cursor offset is out of range")
        if direction == "forward":
            start, end = boundary, min(boundary + limit, total)
        else:
            start, end = max(0, boundary - limit), boundary
        selected: list[list[ModelMessage]] = []
        first_segment_index = None
        offset = 0
        for index, segment in enumerate(segments):
            segment_start = max(start - offset, 0)
            segment_end = min(end - offset, len(segment))
            if segment_start < segment_end or (not segment and start < offset < end):
                if first_segment_index is None:
                    first_segment_index = index
                selected.append(segment[segment_start:segment_end])
            offset += len(segment)
        return messages, HistoryPage(
            segments=selected,
            first_segment_index=first_segment_index,
            next_cursor=self._encode_cursor(segment_count, message_count, end) if end < total else None,
            previous_cursor=self._encode_cursor(segment_count, message_count, start) if start > 0 else None,
            has_more=end < total if direction == "forward" else start > 0,
        )

    @classmethod
    def list_sessions(cls, workspace: Path) -> list[tuple[SessionStore, dict]]:
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
            meta["title"] = _first_user_text(messages) or "(空会话)"
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
            "title": old.get("title") or _first_user_text(messages),
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


def _first_user_text(messages: list[ModelMessage], limit: int = 30) -> str | None:
    """第一条用户消息的截断文本；没有用户消息返回 None。"""
    for msg in messages:
        if is_file_monitor_message(msg):
            continue
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    text = part.content.replace("\n", " ")
                    return text[:limit] + ("…" if len(text) > limit else "")
    return None


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
