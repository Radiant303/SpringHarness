"""会话存储客户端：sessions/messages 两表的读写全部经内部 HTTP API 完成。

语义约定：段自增、title 首写、段列表装段（含空段）、游标分页。
端点一览（X-Internal-Token 鉴权）：

- POST /internal/sessions                         建行（current_segment=0, status=active）
- GET  /internal/sessions/{id}                    打开/查询（404 → None）
- GET  /internal/users/{userId}/sessions          列表（status != deleted, updated_at desc）
- GET  /internal/sessions/{id}/messages           全量消息（段内按 id 升序，payload 为原始消息 JSON）
- POST /internal/sessions/{id}/messages           追加（newSegment 控制开新段；段自增、title IS NULL
                                                   时写入、updated_at 推进在服务端单事务内完成）
- POST /internal/sessions/{id}/delete             软删除（404 → False）
"""

from __future__ import annotations

import datetime
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic_ai import ModelMessage
from pydantic_ai.messages import ModelMessagesTypeAdapter

from spring_harness.cloud.db import STATUS_ACTIVE
from spring_harness.core.config.settings import config
from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.store.paging import first_user_text, page_history


def _dump_message(message: ModelMessage) -> dict:
    """单条消息 dump 成 JSON 对象（与 jsonl 的 _dump_line 同一 wire 格式）。"""
    return ModelMessagesTypeAdapter.dump_python([message], mode="json")[0]


def _load_message(payload: dict) -> ModelMessage:
    return ModelMessagesTypeAdapter.validate_python([payload])[0]


def _parse_utc(value: str) -> datetime.datetime:
    """ISO 串（…Z）→ naive UTC datetime；带偏移的串先归一到 UTC 再去时区，
    与 DATETIME 列（naive UTC）的存取语义一致。"""
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.UTC).replace(tzinfo=None)
    return parsed


# ---- 共享 HTTP client（懒加载单例；store 调用方本来就是同步阻塞形状）----

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _get_client() -> httpx.Client:
    """进程内共享的同步 client：连接池复用，不随 store 对象创建销毁。"""
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                base_url=config.cloud.gateway_base_url,
                headers={"X-Internal-Token": config.cloud.internal_token},
                timeout=10,
            )
        return _client


@dataclass(frozen=True)
class GatewaySessionRow:
    """内部接口返回的会话行。

    user_id/status 供归属校验；详情响应未承诺带 userId，缺失即 None。
    """

    id: str
    user_id: int | None
    title: str | None
    workspace_path: str
    current_segment: int
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_payload(cls, payload: dict) -> GatewaySessionRow:
        return cls(
            id=payload["sessionId"],
            # 详情响应未承诺带 userId：缺失即 None，按越权处理
            user_id=payload.get("userId"),
            title=payload.get("title"),
            workspace_path=payload.get("workspacePath", ""),
            current_segment=payload.get("currentSegment", 0),
            status=payload.get("status", STATUS_ACTIVE),
            created_at=_parse_utc(payload["createdAt"]),
            updated_at=_parse_utc(payload["updatedAt"]),
        )


class GatewaySessionStore:
    """会话存储实现：所有读写操作经内部 HTTP API 完成。"""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @classmethod
    def create(
        cls,
        user_id: int,
        workspace: Path,
        session_id: str | None = None,
    ) -> GatewaySessionStore:
        """建 sessions 行（current_segment=0，status=active，created_at/updated_at 由服务端填）。

        session_id 可显式传入：调用方已用同一 id 分配好工作区目录时传入，
        保证会话 id 与工作区目录名一致；缺省生成 uuid4。
        """
        session_id = session_id or str(uuid.uuid4())
        response = _get_client().post("/internal/sessions", json={
            "sessionId": session_id,
            "userId": user_id,
            "workspacePath": str(workspace),
        })
        response.raise_for_status()
        return cls(session_id)

    @classmethod
    def open(cls, session_id: str) -> GatewaySessionStore | None:
        """打开已存在的会话；sessions 行不存在（如已物理删除）时返回 None。"""
        response = _get_client().get(f"/internal/sessions/{session_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return cls(session_id)

    def append(self, messages: list[ModelMessage]) -> None:
        """每轮结束（含异常终止）后调用，追加到当前段。"""
        self._write(messages, new_segment=False)

    def append_rewritten(self, messages: list[ModelMessage]) -> None:
        """历史被压缩/消息合并改写时调用：服务端把 current_segment 自增后整体写入新段，
        旧段保留备查。"""
        self._write(messages, new_segment=True)

    def _write(self, messages: list[ModelMessage], *, new_segment: bool) -> None:
        # 每批 append 都用首批用户消息算一次 title 候选一并提交；
        # 服务端只在 title 为空时采纳，已有 title 的会话不受影响
        response = _get_client().post(
            f"/internal/sessions/{self._session_id}/messages",
            json={
                "newSegment": new_segment,
                "title": first_user_text(messages),
                "messages": [_dump_message(message) for message in messages],
            },
        )
        if response.status_code == 404:
            raise ValueError(f"会话不存在: {self._session_id}")
        response.raise_for_status()

    def _load_segments(self) -> list[list[ModelMessage]]:
        """读出全部段：段数 = currentSegment + 1（含空段）。"""
        response = _get_client().get(f"/internal/sessions/{self._session_id}/messages")
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
        segments: list[list[ModelMessage]] = [[] for _ in range(data["currentSegment"] + 1)]
        for item in data["messages"]:
            segments[item["segmentNo"]].append(_load_message(item["payload"]))
        return segments

    def load_messages(self) -> list[ModelMessage]:
        """发给模型的当前历史：最大 segment_no 段（rewrite 后的新基线）。"""
        segments = self._load_segments()
        return segments[-1] if segments else []

    def query_history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> tuple[list[ModelMessage], HistoryPage]:
        return page_history(self._load_segments(), self._session_id, cursor, limit, direction)


# ---- 按 user_id 的会话查询 ----


def list_sessions_for_user(user_id: int) -> list[GatewaySessionRow]:
    """当前用户未删除的会话，按 updated_at 倒序（服务端已过滤 deleted 并排序）。"""
    response = _get_client().get(f"/internal/users/{user_id}/sessions")
    response.raise_for_status()
    return [GatewaySessionRow.from_payload(item) for item in response.json()]


def find_active_session(session_id: str, user_id: int) -> GatewaySessionRow | None:
    """按 (session_id, user_id, status=active) 查找；越权与不存在一律返回 None，
    由调用方统一回 404 / SESSION_NOT_FOUND，不区分两种失败以防 IDOR 探测。"""
    response = _get_client().get(f"/internal/sessions/{session_id}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    row = GatewaySessionRow.from_payload(response.json())
    # 归属/状态在本地复核：详情响应不带 userId 或 status 非 active 一律按越权拒绝
    if row.user_id != user_id or row.status != STATUS_ACTIVE:
        return None
    return row


def soft_delete_session(session_id: str, user_id: int) -> bool:
    """软删除：服务端置 status=deleted 并推进 updated_at；行不存在（404）时返回 False。"""
    response = _get_client().post(
        f"/internal/sessions/{session_id}/delete", json={"userId": user_id},
    )
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True
