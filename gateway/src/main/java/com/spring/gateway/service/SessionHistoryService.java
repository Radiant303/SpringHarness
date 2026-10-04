package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.UnknownSessionException;
import com.spring.gateway.entity.Message;
import com.spring.gateway.entity.Session;
import com.spring.gateway.mapper.MessageMapper;
import com.spring.gateway.mapper.SessionMapper;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

/**
 * 会话历史分页：把 Python 侧 core/store/paging.py 的分页语义（跨段去重、游标编解码、
 * raw_segments 切片）原样移植到网关，使 WS 的 session/history 拦截后本地应答与
 * 引擎透传时的结果逐字段一致。
 *
 * <p>段装载语义与 Python 的 MysqlSessionStore._load_segments 一致：段数 =
 * current_segment + 1（含空段），messages 按 (segment_no, id) 升序装入对应段；
 * 段内消息就是 payload 原文（JsonNode），不解析其结构。</p>
 *
 * <p>分页核心是包私有的纯静态方法：不依赖 DB 与 Spring，单元测试直接喂构造的段数据。</p>
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Service
public class SessionHistoryService {

    /** 游标载荷版本：结构不兼容升级时 +1，旧游标按 invalid 拒绝（与 Python CURSOR_VERSION 对齐） */
    private static final int CURSOR_VERSION = 1;

    /** JSON-RPC 错误码：会话不存在（与 Python engine/server.py 的 SESSION_NOT_FOUND 对齐） */
    public static final int SESSION_NOT_FOUND = -32002;

    private final SessionMapper sessionMapper;
    private final MessageMapper messageMapper;
    private final ObjectMapper objectMapper;

    public SessionHistoryService(SessionMapper sessionMapper, MessageMapper messageMapper,
                                 ObjectMapper objectMapper) {
        this.sessionMapper = sessionMapper;
        this.messageMapper = messageMapper;
        this.objectMapper = objectMapper;
    }

    /**
     * 归属校验后本地分页查询会话历史
     *
     * @param sessionId 会话 ID
     * @param userId    当前用户 ID
     * @param cursor    分页游标，可为 null（null 从对应方向的端点开始）
     * @param limit     每页消息数，null 表示完整历史（此时不接受 cursor）
     * @param direction 翻页方向：forward / backward
     * @return JSON-RPC result 节点：segments / firstSegmentIndex / nextCursor / previousCursor / hasMore
     * @throws UnknownSessionException    会话不存在、不属于该用户或已删除（-32002）
     * @throws IllegalArgumentException 参数或游标非法（-32602），消息与 Python 侧一致
     */
    public ObjectNode queryHistory(String sessionId, Long userId, String cursor, Integer limit, String direction) {
        Session row = sessionMapper.selectOne(new LambdaQueryWrapper<Session>()
                .eq(Session::getId, sessionId)
                .eq(Session::getUserId, userId)
                .eq(Session::getStatus, Session.STATUS_ACTIVE));
        if (row == null) {
            throw new UnknownSessionException(sessionId);
        }
        List<Message> rows = messageMapper.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getSessionId, sessionId)
                .orderByAsc(Message::getSegmentNo)
                .orderByAsc(Message::getId));
        HistoryPage page = pageHistory(objectMapper, loadSegments(row, rows), sessionId, cursor, limit, direction);
        return buildResult(objectMapper, page);
    }

    /** 把 messages 行按 (segment_no, id) 装入段列表：段数 = current_segment + 1（含空段） */
    private List<List<JsonNode>> loadSegments(Session row, List<Message> rows) {
        int currentSegment = row.getCurrentSegment() == null ? 0 : row.getCurrentSegment();
        List<List<JsonNode>> segments = new ArrayList<>(currentSegment + 1);
        for (int i = 0; i <= currentSegment; i++) {
            segments.add(new ArrayList<>());
        }
        for (Message item : rows) {
            int segmentNo = item.getSegmentNo() == null ? -1 : item.getSegmentNo();
            if (segmentNo < 0 || segmentNo >= segments.size()) {
                // 数据越界（库被绕过写入时）：跳过而不是越界崩溃
                continue;
            }
            segments.get(segmentNo).add(readPayload(objectMapper, item.getPayload()));
        }
        return segments;
    }

    private static JsonNode readPayload(ObjectMapper objectMapper, String payload) {
        try {
            return objectMapper.readTree(payload);
        } catch (Exception e) {
            throw new IllegalArgumentException("message payload is not valid json");
        }
    }

    // ---- 分页核心：core/store/paging.py 的忠实移植，纯静态、不依赖 DB ----

    /**
     * 对 raw_segments 分页切片。游标编码版本、会话 ID、存储段数、原始消息数、去重后消息边界。
     * 存储前缀固定快照，后续追加和 rewrite 不改变既有分页；新查询用空游标。
     * forward 包含边界后的消息，backward 包含边界之前的消息，结果始终正序。
     * limit=null 返回完整当前历史，此时不接受 cursor。
     */
    static HistoryPage pageHistory(ObjectMapper objectMapper, List<List<JsonNode>> rawSegments, String sessionId,
                                   String cursor, Integer limit, String direction) {
        if (!"forward".equals(direction) && !"backward".equals(direction)) {
            throw new IllegalArgumentException("invalid history direction");
        }
        if (limit != null && limit < 1) {
            throw new IllegalArgumentException("invalid history limit");
        }
        if (cursor != null && limit == null) {
            throw new IllegalArgumentException("history cursor requires a limit");
        }
        CursorPosition position = cursor == null ? null : decodeCursor(objectMapper, cursor, sessionId);
        int segmentCount = rawSegments.size();
        int messageCount = count(rawSegments);
        List<List<JsonNode>> snapshot = rawSegments;
        if (position != null) {
            segmentCount = position.segmentCount();
            messageCount = position.messageCount();
            if (segmentCount > rawSegments.size()) {
                throw new IllegalArgumentException("history cursor snapshot is out of range");
            }
            // 快照只截外层 list：段内 list 仍与原始数据共享（Python slice 语义），只读不改
            snapshot = new ArrayList<>(rawSegments.subList(0, segmentCount));
            int precedingCount = snapshot.isEmpty() ? 0 : count(snapshot.subList(0, snapshot.size() - 1));
            if (messageCount < precedingCount || messageCount > count(snapshot)) {
                throw new IllegalArgumentException("history cursor snapshot is out of range");
            }
            if (!snapshot.isEmpty()) {
                int keep = messageCount - precedingCount;
                List<JsonNode> tail = snapshot.get(snapshot.size() - 1);
                snapshot.set(snapshot.size() - 1, new ArrayList<>(tail.subList(0, keep)));
            }
        }
        List<List<JsonNode>> segments = dedupSegments(snapshot);
        int total = count(segments);
        if (limit == null) {
            return new HistoryPage(total == 0 ? List.of() : segments, total == 0 ? null : 0, null, null, false);
        }
        int boundary = position != null ? position.offset()
                : ("backward".equals(direction) ? total : 0);
        if (boundary > total) {
            throw new IllegalArgumentException("history cursor offset is out of range");
        }
        int start;
        int end;
        if ("forward".equals(direction)) {
            // limit 可能顶到 Integer.MAX_VALUE，边界相加用 long 防溢出
            start = boundary;
            end = (int) Math.min((long) boundary + limit, total);
        } else {
            start = (int) Math.max(0L, (long) boundary - limit);
            end = boundary;
        }
        List<List<JsonNode>> selected = new ArrayList<>();
        Integer firstSegmentIndex = null;
        int offset = 0;
        for (int index = 0; index < segments.size(); index++) {
            List<JsonNode> segment = segments.get(index);
            int segmentStart = Math.max(start - offset, 0);
            int segmentEnd = Math.min(end - offset, segment.size());
            // 空段特例：窗口 strictly 覆盖该段的偏移区间时也要占位，保证 firstSegmentIndex 指向真实段
            if (segmentStart < segmentEnd || (segment.isEmpty() && start < offset && offset < end)) {
                if (firstSegmentIndex == null) {
                    firstSegmentIndex = index;
                }
                selected.add(new ArrayList<>(segment.subList(segmentStart, segmentEnd)));
            }
            offset += segment.size();
        }
        String nextCursor = end < total
                ? encodeCursor(objectMapper, sessionId, segmentCount, messageCount, end) : null;
        String previousCursor = start > 0
                ? encodeCursor(objectMapper, sessionId, segmentCount, messageCount, start) : null;
        boolean hasMore = "forward".equals(direction) ? end < total : start > 0;
        return new HistoryPage(selected, firstSegmentIndex, nextCursor, previousCursor, hasMore);
    }

    /**
     * 跨段去重：压缩改写后的新基线与旧段尾部有重叠前缀时，剥掉重叠部分。
     * Python 按 ModelMessage 逐一相等比较，这里按 payload 的 JsonNode 深相等比较，
     * 语义等价（payload 是同一序列化器确定性 dump 的）。
     */
    static List<List<JsonNode>> dedupSegments(List<List<JsonNode>> segments) {
        List<List<JsonNode>> result = new ArrayList<>();
        List<JsonNode> acc = new ArrayList<>();
        for (List<JsonNode> seg : segments) {
            int stripLo = 0;
            int stripHi = 0;
            for (int s = 0; s <= Math.min(3, seg.size()); s++) {
                for (int k = Math.min(acc.size(), seg.size() - s); k > 0; k--) {
                    if (overlaps(acc, k, seg, s, k)) {
                        if (s + k > stripHi) {
                            stripLo = s;
                            stripHi = s + k;
                        }
                        break;
                    }
                }
            }
            List<JsonNode> deduped = new ArrayList<>(seg.subList(0, stripLo));
            deduped.addAll(seg.subList(stripHi, seg.size()));
            result.add(deduped);
            acc.addAll(deduped);
        }
        return result;
    }

    /** acc 末尾 k 个元素与 seg 从 segStart 起 k 个元素是否逐条深相等（JsonNode.equals 即结构深相等） */
    private static boolean overlaps(List<JsonNode> acc, int tailSize, List<JsonNode> seg, int segStart, int k) {
        for (int i = 0; i < k; i++) {
            JsonNode left = acc.get(acc.size() - tailSize + i);
            JsonNode right = seg.get(segStart + i);
            if (!left.equals(right)) {
                return false;
            }
        }
        return true;
    }

    /**
     * 把分页边界编码进游标：base64url（无 padding）的紧凑 JSON
     * {@code [1, sessionId, segmentCount, messageCount, offset]}。
     */
    static String encodeCursor(ObjectMapper objectMapper, String sessionId, int segmentCount, int messageCount,
                               int offset) {
        String payload = objectMapper.writeValueAsString(
                List.of(CURSOR_VERSION, sessionId, segmentCount, messageCount, offset));
        return Base64.getUrlEncoder().withoutPadding().encodeToString(payload.getBytes(StandardCharsets.UTF_8));
    }

    /** 解码并校验游标：版本号与会话 ID 不匹配、下标非负性不满足都按 invalid 拒绝 */
    private static CursorPosition decodeCursor(ObjectMapper objectMapper, String cursor, String sessionId) {
        JsonNode data;
        try {
            data = objectMapper.readTree(Base64.getUrlDecoder().decode(cursor));
        } catch (Exception e) {
            throw new IllegalArgumentException("invalid history cursor");
        }
        if (!data.isArray() || data.size() != 5) {
            throw new IllegalArgumentException("invalid history cursor");
        }
        JsonNode versionNode = data.get(0);
        if (!versionNode.isInt() || versionNode.asInt() != CURSOR_VERSION) {
            throw new IllegalArgumentException("invalid history cursor");
        }
        JsonNode sessionIdNode = data.get(1);
        if (!sessionIdNode.isTextual() || !sessionId.equals(sessionIdNode.asText())) {
            throw new IllegalArgumentException("invalid history cursor");
        }
        // Python 要求 type(value) is int（拒绝 bool 与 float）且非负；超出 long 的大整数按越界游标走
        long[] values = new long[3];
        for (int i = 0; i < values.length; i++) {
            JsonNode node = data.get(2 + i);
            if (!node.isIntegralNumber() || !node.canConvertToExactIntegral() || node.asLong() < 0) {
                throw new IllegalArgumentException("invalid history cursor");
            }
            values[i] = node.asLong();
        }
        return new CursorPosition(toInt(values[0]), toInt(values[1]), toInt(values[2]));
    }

    /** 超 int 范围的下标按上界截断：后续与真实段数/消息数比较时仍会判为越界游标 */
    private static int toInt(long value) {
        return value > Integer.MAX_VALUE ? Integer.MAX_VALUE : (int) value;
    }

    private static int count(List<List<JsonNode>> segments) {
        int total = 0;
        for (List<JsonNode> segment : segments) {
            total += segment.size();
        }
        return total;
    }

    /** 组装 JSON-RPC result；四个键始终存在（null 也序列化），与 Python 侧 HistoryResult 一致 */
    static ObjectNode buildResult(ObjectMapper objectMapper, HistoryPage page) {
        ObjectNode result = objectMapper.createObjectNode();
        ArrayNode segments = result.putArray("segments");
        for (List<JsonNode> segment : page.segments()) {
            ArrayNode item = segments.addArray();
            for (JsonNode message : segment) {
                item.add(message);
            }
        }
        result.put("firstSegmentIndex", page.firstSegmentIndex());
        result.put("nextCursor", page.nextCursor());
        result.put("previousCursor", page.previousCursor());
        result.put("hasMore", page.hasMore());
        return result;
    }

    /**
     * 一页历史快照（core/history.py 的 HistoryPage 对应物）。
     *
     * @param segments           选中段的消息切片（段内为追加序）
     * @param firstSegmentIndex 选中第一个非空切片的段下标，无则为 null
     * @param nextCursor         向前续取的游标，无更多则 null
     * @param previousCursor     向后续取的游标，无更早则 null
     * @param hasMore            对应请求方向是否还有更多
     */
    record HistoryPage(List<List<JsonNode>> segments, Integer firstSegmentIndex,
                       String nextCursor, String previousCursor, boolean hasMore) {
    }

    /**
     * 游标里的存储快照：段数、原始消息数、去重后消息边界。
     *
     * @param segmentCount 存储段数
     * @param messageCount 原始消息数
     * @param offset       去重后消息边界
     */
    private record CursorPosition(int segmentCount, int messageCount, int offset) {
    }
}
