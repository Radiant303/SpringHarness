"""会话历史的存储介质无关逻辑：跨段去重、游标编解码、raw_segments 分页切片。

各存储实现只负责把介质读成 list[list[ModelMessage]]（段列表，段内为追加序），
分页语义统一在这里实现：jsonl（每会话一个文件）与 mysql（sessions/messages 两表）
因此拥有完全一致的游标格式与分页行为。
"""
from __future__ import annotations

import base64
import json

from pydantic_ai import ModelMessage, ModelRequest, UserPromptPart

from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.hooks.model import is_auto_injected_message

# 游标载荷版本：结构不兼容升级时 +1，旧游标按 invalid 拒绝
CURSOR_VERSION = 1


def dedup_segments(segments: list[list[ModelMessage]]) -> list[list[ModelMessage]]:
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


def encode_cursor(session_id: str, segment_count: int, message_count: int, offset: int) -> str:
    """把分页边界编码进游标：版本号、会话 ID、存储段数、原始消息数、去重后边界。"""
    payload = json.dumps([CURSOR_VERSION, session_id, segment_count, message_count, offset], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, session_id: str) -> tuple[int, int, int]:
    """解码并校验游标：版本号与会话 ID 不匹配、下标非负性不满足都按 invalid 拒绝。"""
    try:
        payload = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("invalid history cursor") from e
    if (
        not isinstance(data, list) or len(data) != 5
        or type(data[0]) is not int or data[0] != CURSOR_VERSION or data[1] != session_id
        or any(type(value) is not int or value < 0 for value in data[2:])
    ):
        raise ValueError("invalid history cursor")
    return data[2], data[3], data[4]


def first_user_text(messages: list[ModelMessage], limit: int = 30) -> str | None:
    """第一条用户消息的截断文本（跳过系统自动注入的消息）。"""
    for msg in messages:
        if is_auto_injected_message(msg):
            continue
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    text = part.content.replace("\n", " ")
                    return text[:limit] + ("…" if len(text) > limit else "")
    return None


def page_history(
    raw_segments: list[list[ModelMessage]],
    session_id: str,
    cursor: str | None = None,
    limit: int | None = None,
    direction: HistoryDirection = "forward",
) -> tuple[list[ModelMessage], HistoryPage]:
    """对 raw_segments 分页切片，返回（发给模型的当前历史, 分页历史快照）。

    游标编码版本、会话 ID、存储段数、原始消息数、去重后消息边界。
    存储前缀固定快照，后续追加和 rewrite 不改变既有分页；新查询用空游标。
    forward 包含边界后的消息，backward 包含边界之前的消息，结果始终正序。
    limit=None 返回完整当前历史，此时不接受 cursor。
    """
    if direction not in {"forward", "backward"}:
        raise ValueError("invalid history direction")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("invalid history limit")
    if cursor is not None and limit is None:
        raise ValueError("history cursor requires a limit")
    position = decode_cursor(cursor, session_id) if cursor is not None else None
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
    segments = dedup_segments(snapshot)
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
        next_cursor=encode_cursor(session_id, segment_count, message_count, end) if end < total else None,
        previous_cursor=encode_cursor(session_id, segment_count, message_count, start) if start > 0 else None,
        has_more=end < total if direction == "forward" else start > 0,
    )
