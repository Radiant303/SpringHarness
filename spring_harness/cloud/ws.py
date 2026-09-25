from __future__ import annotations

import asyncio
import threading
import uuid
from pathlib import Path
from typing import ClassVar

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, sessionmaker

from spring_harness.cloud.auth import decode_user_id
from spring_harness.cloud.db import get_sessionmaker
from spring_harness.core.config.settings import config
from spring_harness.core.log import logger
from spring_harness.core.rpc.connection import JsonRpcConnection, JsonRpcError
from spring_harness.core.rpc.schema import (
    AttachParams,
    SessionListResult,
    SessionResult,
    SessionSummary,
    WorkspaceParams,
)
from spring_harness.core.rpc.server import (
    PROTOCOL_VERSION,
    SESSION_NOT_FOUND,
    AppServer,
)
from spring_harness.core.services.web_server import WebInitializeResult, _model_infos
from spring_harness.core.store.mysql import (
    MysqlSessionStore,
    find_active_session,
    list_sessions_for_user,
)

# 会话已被其他连接占用（同会话串行的进程内拒绝码）
SESSION_OCCUPIED = -32003

WS_UNAUTHORIZED_CLOSE_CODE = 4401


class CloudAppServer(AppServer):
    """按 user_id 隔离的 JSON-RPC 协议面：会话归属 MySQL，工作区由服务端分配。"""

    # 类级别注册表：session_id -> 持有它的连接（进程内"同会话串行"锁）
    _active_owners: ClassVar[dict[str, CloudAppServer]] = {}
    _active_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        connection: JsonRpcConnection,
        *,
        user_id: int,
        session_factory: sessionmaker[Session],
        data_root: Path,
    ) -> None:
        super().__init__(connection)
        self._user_id = user_id
        self._db = session_factory
        self._data_root = data_root
        # 本连接登记的会话：连接关闭时统一注销
        self._owned_sessions: set[str] = set()

    @property
    def _user_root(self) -> Path:
        return self._data_root / "workspaces" / str(self._user_id)

    # ---- 注册表：进程内同会话串行 ----

    def _acquire(self, session_id: str) -> None:
        """登记会话占用；已被别的连接持有则拒绝。同步临界区，无 await 穿插。"""
        with CloudAppServer._active_lock:
            owner = CloudAppServer._active_owners.get(session_id)
            if owner is not None and owner is not self:
                raise JsonRpcError(SESSION_OCCUPIED, "会话正被其他连接使用")
            CloudAppServer._active_owners[session_id] = self
            self._owned_sessions.add(session_id)

    def _release(self, session_id: str) -> None:
        with CloudAppServer._active_lock:
            if CloudAppServer._active_owners.get(session_id) is self:
                del CloudAppServer._active_owners[session_id]
            self._owned_sessions.discard(session_id)

    # ---- 方法实现：全部改按 user_id 操作 MySQL ----

    async def _initialize(self, _: None) -> WebInitializeResult:
        # workspace 上报用户云端根目录：前端只拿它做展示与请求参数，服务端忽略
        return WebInitializeResult(
            server_name="spring-harness",
            protocol_version=PROTOCOL_VERSION,
            workspace=str(self._user_root),
            models=_model_infos(),
            default_model=config.default_model,
        )

    async def _session_new(self, p: WorkspaceParams) -> SessionResult:
        session_id = str(uuid.uuid4())
        workspace = self._user_root / session_id
        await asyncio.to_thread(workspace.mkdir, parents=True, exist_ok=True)
        store = await asyncio.to_thread(
            MysqlSessionStore.create, self._db, self._user_id, workspace, session_id,
        )
        session = await self._create_session(workspace, store, p.model)
        self._acquire(session.session_id)
        return SessionResult(session_id=session.session_id)

    async def _session_resume_last(self, p: WorkspaceParams) -> SessionResult:
        rows = await asyncio.to_thread(list_sessions_for_user, self._db, self._user_id)
        if not rows:
            return SessionResult(session_id=None)
        target = rows[0]
        existing = next(
            (s for s in self._sessions.values() if s.session_id == target.id), None,
        )
        if existing is not None:
            self._apply_model(existing, p.model)
            return SessionResult(session_id=existing.session_id)
        self._acquire(target.id)
        try:
            store = await asyncio.to_thread(MysqlSessionStore.open, self._db, target.id)
            if store is None:  # 理论不可达：刚才还在列表里
                raise JsonRpcError(SESSION_NOT_FOUND, f"未知会话: {target.id}")
            session = await self._create_session(Path(target.workspace_path), store, p.model)
        except BaseException:
            self._release(target.id)
            raise
        return SessionResult(session_id=session.session_id)

    async def _session_list(self, p: WorkspaceParams) -> SessionListResult:
        rows = await asyncio.to_thread(list_sessions_for_user, self._db, self._user_id)
        return SessionListResult(sessions=[
            SessionSummary(
                session_id=row.id,
                title=row.title,
                # naive UTC 补 "Z"：避免前端按本地时区解析
                created_at=row.created_at.isoformat() + "Z",
                updated_at=row.updated_at.isoformat() + "Z",
            )
            for row in rows
        ])

    async def _session_attach(self, p: AttachParams) -> SessionResult:
        existing = next(
            (s for s in self._sessions.values() if s.session_id == p.session_id), None,
        )
        if existing is not None:
            self._apply_model(existing, p.model)
            return SessionResult(session_id=existing.session_id)
        row = await asyncio.to_thread(
            find_active_session, self._db, p.session_id, self._user_id,
        )
        if row is None:
            raise JsonRpcError(SESSION_NOT_FOUND, f"未知会话: {p.session_id}")
        # 先占位再建会话：抢失败直接拒绝，不会留下半建的 HarnessSession
        self._acquire(p.session_id)
        try:
            store = await asyncio.to_thread(MysqlSessionStore.open, self._db, p.session_id)
            if store is None:  # 理论不可达：find_active_session 已确认存在
                raise JsonRpcError(SESSION_NOT_FOUND, f"未知会话: {p.session_id}")
            session = await self._create_session(Path(row.workspace_path), store, p.model)
        except BaseException:
            self._release(p.session_id)
            raise
        return SessionResult(session_id=session.session_id)

    async def shutdown(self) -> None:
        await super().shutdown()
        for session_id in tuple(self._owned_sessions):
            self._release(session_id)


async def ws_endpoint(websocket: WebSocket) -> None:
    """握手时验 token 得 user_id，无效则 close(4401)；之后照 web_server 模式接 JsonRpcConnection。"""
    await websocket.accept()
    token = websocket.query_params.get("token")
    user_id = decode_user_id(token) if token else None
    if user_id is None:
        await websocket.close(code=WS_UNAUTHORIZED_CLOSE_CODE)
        return

    async def read_line() -> str | None:
        try:
            return await websocket.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            return None  # 对端关闭 = EOF，驱动 connection.run 收尾

    async def write_line(line: str) -> None:
        try:
            await websocket.send_text(line)
        except (WebSocketDisconnect, RuntimeError) as e:
            try:
                await websocket.close()
            except (WebSocketDisconnect, RuntimeError):
                pass
            raise ConnectionError("WebSocket 已关闭") from e

    connection = JsonRpcConnection(read_line, write_line)
    server = CloudAppServer(
        connection,
        user_id=user_id,
        session_factory=get_sessionmaker(),
        data_root=Path(config.cloud.data_root).expanduser(),
    )
    logger.info("云端客户端已连接: user_id={} client={}", user_id, websocket.client)
    try:
        await connection.run(server.handle_request, server.handle_notification)
    finally:
        await server.shutdown()
        logger.info("云端客户端已断开: user_id={} client={}", user_id, websocket.client)
