package com.spring.gateway.ws;

import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.connection.Limit;
import org.springframework.data.domain.Range;
import org.springframework.data.domain.Range.Bound;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * 事件流推送器：按订阅从 Redis Stream 阻塞读会话事件，推给浏览器 WS。
 *
 * <p>条目字段 event 为事件 JSON，推送帧在 params 上多带一个 seq（Stream 条目 ID）作为续读游标。
 *
 * <p>起始位置两种语义：
 * <ul>
 *   <li>lastSeq 非 null（同页断线重连）：从该条目之后精确续读，零重放；
 *   <li>lastSeq 为 null（整页刷新，内存游标丢失）：反向扫描找到最近一条
 *   turn_finished，从其之后重放——当前未完成的 turn 从它自己的开头完整重放，
 *   已完成的 turn 不会重放（历史由数据库负责）。
 * </ul>
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Component
public class TurnStreamReader {

    private static final String KEY_PREFIX = "stream:session:";
    private static final int READ_BATCH = 500;
    private static final Duration READ_BLOCK = Duration.ofSeconds(2);
    private static final long ERROR_BACKOFF_MS = 1000;
    /** 反向扫描每页条目数（找最近一条 turn_finished） */
    private static final int SCAN_PAGE = 500;

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final ExecutorService executor;
    /** 浏览器连接 ID → (会话 ID → 读取任务) */
    private final Map<String, Map<String, Future<?>>> readers = new ConcurrentHashMap<>();

    public TurnStreamReader(StringRedisTemplate redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.executor = Executors.newCachedThreadPool(runnable -> {
            Thread thread = new Thread(runnable, "turn-stream-reader");
            thread.setDaemon(true);
            return thread;
        });
    }

    /**
     * 订阅某会话的事件流；同连接同会话重复订阅会替换旧读取任务
     *
     * @param browserSession 浏览器 WS 会话
     * @param sessionId      会话 ID
     * @param lastSeq        续读游标（Stream 条目 ID），null 表示只收新事件
     */
    public void subscribe(WebSocketSession browserSession, String sessionId, String lastSeq) {
        Map<String, Future<?>> bySession =
                readers.computeIfAbsent(browserSession.getId(), key -> new ConcurrentHashMap<>());
        Future<?> previous = bySession.remove(sessionId);
        if (previous != null) {
            previous.cancel(true);
        }
        bySession.put(sessionId, executor.submit(() -> readLoop(browserSession, sessionId, lastSeq)));
        log.info("stream 订阅: browser={} session={} from={}",
                browserSession.getId(), sessionId, lastSeq == null ? "$" : lastSeq);
    }

    /** 连接关闭时取消它的全部读取任务 */
    public void closeFor(WebSocketSession browserSession) {
        Map<String, Future<?>> bySession = readers.remove(browserSession.getId());
        if (bySession != null) {
            bySession.values().forEach(future -> future.cancel(true));
        }
    }

    @PreDestroy
    public void shutdown() {
        executor.shutdownNow();
    }

    private void readLoop(WebSocketSession browserSession, String sessionId, String lastSeq) {
        String key = KEY_PREFIX + sessionId;
        String offset = lastSeq != null ? lastSeq : findTurnStartOffset(key);
        while (browserSession.isOpen() && !Thread.currentThread().isInterrupted()) {
            List<MapRecord<String, Object, Object>> records;
            try {
                records = redisTemplate.opsForStream().read(
                        StreamReadOptions.empty().count(READ_BATCH).block(READ_BLOCK),
                        StreamOffset.create(key,
                                offset == null ? ReadOffset.latest() : ReadOffset.from(offset)));
            } catch (Exception e) {
                // 取消（连接关闭/重复订阅）时中断阻塞读会抛异常，属正常退出
                if (Thread.currentThread().isInterrupted() || !browserSession.isOpen()) {
                    break;
                }
                log.warn("stream 读取异常: session={} error={}", sessionId, e.getMessage());
                sleepQuietly();
                continue;
            }
            if (records == null) {
                continue;  // 阻塞读超时，无新事件
            }
            for (MapRecord<String, Object, Object> record : records) {
                offset = record.getId().getValue();
                Object eventJson = record.getValue().get("event");
                if (eventJson != null) {
                    push(browserSession, sessionId, offset, eventJson.toString());
                }
            }
        }
    }

    /**
     * lastSeq 缺失时确定起始位置：反向扫描找最近一条 turn_finished，从其后重放
     * 当前未完成的 turn；流非空但没有 turn_finished → 返回 "0"（整个流就是当前
     * turn，从头放）；流为空/不存在 → 返回 null（只收新事件）。
     */
    private String findTurnStartOffset(String key) {
        String upperExclusive = null;
        while (true) {
            Range<String> range = upperExclusive == null
                    ? Range.unbounded()
                    : Range.from(Bound.inclusive("-")).to(Bound.exclusive(upperExclusive));
            List<MapRecord<String, Object, Object>> page;
            try {
                page = redisTemplate.opsForStream().reverseRange(key, range, Limit.limit().count(SCAN_PAGE));
            } catch (Exception e) {
                log.warn("stream 反向扫描失败: key={} error={}", key, e.getMessage());
                return null;
            }
            if (page == null || page.isEmpty()) {
                return null;
            }
            for (MapRecord<String, Object, Object> record : page) {  // reverseRange 返回新→旧
                Object eventJson = record.getValue().get("event");
                if (eventJson != null && isTurnFinished(eventJson.toString())) {
                    return record.getId().getValue();
                }
            }
            if (page.size() < SCAN_PAGE) {
                return "0";  // 扫到流头也没见到 turn_finished：流里全是当前 turn
            }
            upperExclusive = page.get(page.size() - 1).getId().getValue();
        }
    }

    private boolean isTurnFinished(String eventJson) {
        try {
            JsonNode kind = objectMapper.readTree(eventJson).get("kind");
            return kind != null && "turn_finished".equals(kind.asText());
        } catch (Exception e) {
            return false;
        }
    }

    private void push(WebSocketSession browserSession, String sessionId, String seq, String eventJson) {
        try {
            ObjectNode params = objectMapper.createObjectNode();
            params.put("sessionId", sessionId);
            params.put("seq", seq);
            params.set("event", objectMapper.readTree(eventJson));
            ObjectNode frame = objectMapper.createObjectNode();
            frame.put("jsonrpc", "2.0");
            frame.put("method", "session/event");
            frame.set("params", params);
            // 同一浏览器会话存在多个发送方，发送必须串行，避免帧交错
            synchronized (browserSession) {
                if (browserSession.isOpen()) {
                    browserSession.sendMessage(new TextMessage(objectMapper.writeValueAsString(frame)));
                }
            }
        } catch (Exception e) {
            log.warn("stream 事件推送失败: session={} seq={} error={}", sessionId, seq, e.getMessage());
        }
    }

    private static void sleepQuietly() {
        try {
            Thread.sleep(ERROR_BACKOFF_MS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
