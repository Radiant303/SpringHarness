import datetime
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from spring_harness.cloud.db import UserRow, get_sessionmaker
from spring_harness.core.config.settings import config

_ALGORITHM = "HS256"
_bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False  # 哈希串损坏：按密码错误处理


def create_token(user_id: int, username: str) -> str:
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": now + datetime.timedelta(minutes=config.cloud.jwt_expire_minutes),
    }
    return jwt.encode(payload, config.cloud.jwt_secret, algorithm=_ALGORITHM)


def decode_user_id(token: str) -> int | None:
    """验签并取 user_id；任何失败（过期/篡改/claims 缺失）返回 None。"""
    try:
        payload = jwt.decode(token, config.cloud.jwt_secret, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def get_session_factory() -> sessionmaker[Session]:
    """FastAPI 依赖：进程内共享的 sessionmaker（指向 cloud 配置的数据库）。"""
    return get_sessionmaker()


def get_current_user(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UserRow:
    """解析 Bearer 令牌并加载用户；失败一律 401（不带 WWW-Authenticate 之外的细节）。"""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "未认证", headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    user_id = decode_user_id(credentials.credentials)
    if user_id is None:
        raise unauthorized
    with factory() as s:
        user = s.get(UserRow, user_id)
    if user is None:
        raise unauthorized
    return user
