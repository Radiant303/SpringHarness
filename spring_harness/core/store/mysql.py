"""MySQL 会话存储：sessions 一行 + messages 多行，语义与 JsonlSessionStore 对齐。

段（segment）映射：jsonl 的 history_rewrite 标记 → sessions.current_segment 自增；
append 追加到 current_segment 段，append_rewritten 开新段整体写入；
"发给模型的当前历史" = 最大 segment_no 的全部行；展示历史 = 全部段 + 共享去重。
query_history 复用 store/paging.py 的分页逻辑：DB 读出的段构造成
list[list[ModelMessage]] 后走同一条代码路径，游标格式与 jsonl 完全一致。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic_ai import ModelMessage
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from spring_harness.cloud.db import (
    STATUS_ACTIVE,
    STATUS_DELETED,
    MessageRow,
    SessionRow,
    utc_now,
)
from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.store.paging import first_user_text, page_history


def _dump_message(message: ModelMessage) -> dict:
    """单条消息 dump 成 JSON 对象（与 jsonl 的 _dump_line 同一 wire 格式）。"""
    return ModelMessagesTypeAdapter.dump_python([message], mode="json")[0]


def _load_message(payload: dict) -> ModelMessage:
    return ModelMessagesTypeAdapter.validate_python([payload])[0]


class MysqlSessionStore:
    """实现 SessionStore Protocol；每次 DB 操作用独立 session，不持有长连接。"""

    def __init__(self, session_factory: sessionmaker[Session], session_id: str) -> None:
        self._session_factory = session_factory
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @classmethod
    def create(
        cls,
        session_factory: sessionmaker[Session],
        user_id: int,
        workspace: Path,
        session_id: str | None = None,
    ) -> MysqlSessionStore:
        """插入 sessions 行（current_segment=0，status=active）。

        session_id 可显式传入：调用方已用同一 id 分配好工作区目录时传入，
        保证会话 id 与工作区目录名一致；缺省生成 uuid4。
        """
        session_id = session_id or str(uuid.uuid4())
        now = utc_now()
        with session_factory() as s:
            s.add(SessionRow(
                id=session_id,
                user_id=user_id,
                workspace_path=str(workspace),
                current_segment=0,
                status=STATUS_ACTIVE,
                created_at=now,
                updated_at=now,
            ))
            s.commit()
        return cls(session_factory, session_id)

    @classmethod
    def open(
        cls, session_factory: sessionmaker[Session], session_id: str,
    ) -> MysqlSessionStore | None:
        """打开已存在的会话；sessions 行不存在（如已物理删除）时返回 None。"""
        with session_factory() as s:
            row = s.get(SessionRow, session_id)
        if row is None:
            return None
        return cls(session_factory, session_id)

    def append(self, messages: list[ModelMessage]) -> None:
        """每轮结束（含异常终止）后调用，追加到当前段。"""
        self._write(messages, new_segment=False)

    def append_rewritten(self, messages: list[ModelMessage]) -> None:
        """历史被压缩/消息合并改写时调用：current_segment 自增后整体写入新段，
        旧段保留备查，与 jsonl 的 history_rewrite 标记语义一致。"""
        self._write(messages, new_segment=True)

    def _write(self, messages: list[ModelMessage], *, new_segment: bool) -> None:
        now = utc_now()
        with self._session_factory() as s:
            row = s.get(SessionRow, self._session_id)
            if row is None:
                raise ValueError(f"会话不存在: {self._session_id}")
            if new_segment:
                row.current_segment += 1
            segment_no = row.current_segment
            # title 只在为空时用首批消息算一次，之后沿用（与 jsonl 索引同语义）
            title = first_user_text(messages) if row.title is None else None
            for message in messages:
                s.add(MessageRow(
                    session_id=self._session_id,
                    segment_no=segment_no,
                    payload=_dump_message(message),
                ))
            row.updated_at = now
            if title is not None:
                row.title = title
            s.commit()

    def _load_segments(self) -> list[list[ModelMessage]]:
        """读出全部段：段数 = current_segment + 1（含空段，与 jsonl 的标记分段一致）。"""
        with self._session_factory() as s:
            row = s.get(SessionRow, self._session_id)
            if row is None:
                return []
            segment_count = row.current_segment + 1
            rows = s.execute(
                select(MessageRow)
                .where(MessageRow.session_id == self._session_id)
                .order_by(MessageRow.segment_no, MessageRow.id)
            ).scalars()
            segments: list[list[ModelMessage]] = [[] for _ in range(segment_count)]
            for item in rows:
                segments[item.segment_no].append(_load_message(item.payload))
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


# ---- 按 user_id 的会话查询（云端 API / WS 协议面用，本地 store 无此概念）----


def get_session(
    session_factory: sessionmaker[Session], session_id: str,
) -> SessionRow | None:
    with session_factory() as s:
        return s.get(SessionRow, session_id)


def list_sessions_for_user(
    session_factory: sessionmaker[Session], user_id: int,
) -> list[SessionRow]:
    """当前用户未删除的会话，按 updated_at 倒序（同秒时按 id 倒序保证确定性）。"""
    with session_factory() as s:
        return list(s.execute(
            select(SessionRow)
            .where(SessionRow.user_id == user_id, SessionRow.status != STATUS_DELETED)
            .order_by(SessionRow.updated_at.desc(), SessionRow.id.desc())
        ).scalars())


def find_active_session(
    session_factory: sessionmaker[Session], session_id: str, user_id: int,
) -> SessionRow | None:
    """按 (session_id, user_id, status=active) 查找；越权与不存在一律返回 None，
    由调用方统一回 404 / SESSION_NOT_FOUND，不区分两种失败以防 IDOR 探测。"""
    with session_factory() as s:
        return s.execute(
            select(SessionRow).where(
                SessionRow.id == session_id,
                SessionRow.user_id == user_id,
                SessionRow.status == STATUS_ACTIVE,
            )
        ).scalar_one_or_none()


def soft_delete_session(
    session_factory: sessionmaker[Session], session_id: str, user_id: int,
) -> bool:
    """软删除：status 置 deleted 并推进 updated_at；行不属于该用户/已删除时返回 False。"""
    with session_factory() as s:
        row = s.get(SessionRow, session_id)
        if row is None or row.user_id != user_id or row.status == STATUS_DELETED:
            return False
        row.status = STATUS_DELETED
        row.updated_at = utc_now()
        s.commit()
        return True
