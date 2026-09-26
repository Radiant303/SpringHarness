import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sqlalchemy.orm import Session, sessionmaker

from spring_harness.cloud import schemas
from spring_harness.cloud.auth import get_current_user, get_session_factory
from spring_harness.cloud.db import SessionRow, UserRow
from spring_harness.core.config.settings import config
from spring_harness.core.store.mysql import (
    MysqlSessionStore,
    find_active_session,
    get_session,
    list_sessions_for_user,
    soft_delete_session,
)

router = APIRouter(prefix="/api", tags=["cloud"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

_SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
_CurrentUser = Annotated[UserRow, Depends(get_current_user)]


def _data_root() -> Path:
    return Path(config.cloud.data_root).expanduser()


def _summary(row: SessionRow) -> schemas.SessionSummary:
    return schemas.SessionSummary(
        session_id=row.id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/sessions", response_model=list[schemas.SessionSummary])
def list_sessions(
    user: _CurrentUser,
    factory: _SessionFactory,
) -> list[schemas.SessionSummary]:
    return [_summary(row) for row in list_sessions_for_user(factory, user.id)]


@router.post(
    "/sessions", status_code=status.HTTP_201_CREATED, response_model=schemas.SessionSummary,
)
def create_session(
    user: _CurrentUser,
    factory: _SessionFactory,
) -> schemas.SessionSummary:
    session_id = str(uuid.uuid4())
    # 工作区只能由服务端分配：{data_root}/workspaces/{user_id}/{session_id}
    workspace = _data_root() / "workspaces" / str(user.id) / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    MysqlSessionStore.create(factory, user.id, workspace, session_id)
    row = get_session(factory, session_id)
    assert row is not None  # 刚刚插入
    return _summary(row)


@router.get("/sessions/{session_id}", response_model=schemas.SessionSummary)
def get_session_detail(
    session_id: str,
    user: _CurrentUser,
    factory: _SessionFactory,
) -> schemas.SessionSummary:
    row = find_active_session(factory, session_id, user.id)
    if row is None:
        raise _NOT_FOUND
    return _summary(row)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    user: _CurrentUser,
    factory: _SessionFactory,
) -> None:
    # 软删除：status 置 deleted；越权/不存在/已删除一律 404
    if not soft_delete_session(factory, session_id, user.id):
        raise _NOT_FOUND


@router.get("/sessions/{session_id}/history", response_model=schemas.HistoryPageResponse)
def session_history(
    session_id: str,
    user: _CurrentUser,
    factory: _SessionFactory,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1),
    direction: Literal["forward", "backward"] = "backward",
) -> schemas.HistoryPageResponse:
    row = find_active_session(factory, session_id, user.id)
    if row is None:
        raise _NOT_FOUND
    store = MysqlSessionStore(factory, session_id)
    try:
        _, page = store.query_history(cursor=cursor, limit=limit, direction=direction)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    # 序列化方式与 rpc/server.py 的 _session_history 保持一致
    return schemas.HistoryPageResponse(
        segments=[
            ModelMessagesTypeAdapter.dump_python(segment, mode="json")
            for segment in page.segments
        ],
        first_segment_index=page.first_segment_index,
        next_cursor=page.next_cursor,
        previous_cursor=page.previous_cursor,
        has_more=page.has_more,
    )
