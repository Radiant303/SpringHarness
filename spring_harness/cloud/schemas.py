import datetime

from pydantic import BaseModel, field_serializer


class SessionSummary(BaseModel):
    session_id: str
    title: str | None = None
    # 存储为 naive UTC（DATETIME 列不带时区）；序列化补 "Z" 标明时区，
    # 否则前端会把 UTC 字符串当本地时间解析，显示偏差 8 小时
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @field_serializer("created_at", "updated_at")
    def _ser_utc(self, value: datetime.datetime) -> str:
        return value.isoformat() + "Z"


class HistoryPageResponse(BaseModel):
    """与 rpc/schema.py 的 HistoryResult 对齐：段内为 dump_python(mode="json") 的消息。"""

    segments: list[list[dict]]
    first_segment_index: int | None = None
    next_cursor: str | None = None
    previous_cursor: str | None = None
    has_more: bool
