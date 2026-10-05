package com.spring.gateway.ws;

import com.spring.gateway.common.BizException;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.common.UnknownSessionException;
import com.spring.gateway.entity.Session;
import com.spring.gateway.service.InternalStoreService;
import com.spring.gateway.service.SessionHistoryService;
import com.spring.gateway.service.TurnDispatchService;
import jakarta.websocket.WebSocketContainer;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/**
 * 聊天 WS 中继：浏览器 ↔ 网关 ↔ 引擎。
 *
 * <p>每条浏览器连接建立一条到引擎 /ws 的客户端连接，文本帧双向透传；
 * token 由握手拦截器校验后原样透传（引擎侧再做一次验签）。
 *
 * <p>turn/start、turn/cancel 请求帧不透传，转为 MQ 消息并本地合成 JSON-RPC 应答，
 * 发布失败时回退为透传；token 流仍由引擎经既有 WS 泵推回。
 *
 * <p>session/list、session/history 为只读查询，网关本地查库合成应答，不再透传。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Component
public class EngineRelayHandler extends TextWebSocketHandler {

    /** 浏览器会话属性键：对应的引擎 WS 会话 */
    private static final String ATTR_ENGINE_SESSION = "engineSession";

    private static final long ENGINE_CONNECT_TIMEOUT_SECONDS = 10;

    /** JSON-RPC 标准错误码：参数不合法 */
    private static final int INVALID_PARAMS = -32602;

    /** JSON-RPC 标准错误码：内部错误 */
    private static final int INTERNAL_ERROR = -32603;

    /** 业务拒绝（积分不足等）：-32000 属 JSON-RPC 保留的服务端错误段 */
    private static final int BIZ_REJECTED = -32000;

    private final String engineWsBase;
    private final ObjectMapper objectMapper;
    private final TurnDispatchService turnDispatchService;
    private final TurnStreamReader turnStreamReader;
    private final InternalStoreService internalStoreService;
    private final SessionHistoryService sessionHistoryService;
    private final WebSocketContainer webSocketContainer;

    public EngineRelayHandler(@Value("${app.engine-base-url}") String engineBaseUrl,
                              ObjectMapper objectMapper,
                              TurnDispatchService turnDispatchService,
                              TurnStreamReader turnStreamReader,
                              InternalStoreService internalStoreService,
                              SessionHistoryService sessionHistoryService,
                              WebSocketContainer webSocketContainer) {
        // http(s)://host:port → ws(s)://host:port
        this.engineWsBase = engineBaseUrl.replaceFirst("^http", "ws");
        this.objectMapper = objectMapper;
        this.turnDispatchService = turnDispatchService;
        this.turnStreamReader = turnStreamReader;
        this.internalStoreService = internalStoreService;
        this.sessionHistoryService = sessionHistoryService;
        this.webSocketContainer = webSocketContainer;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession browserSession) throws Exception {
        // 幽灵用户（签名有效、库中无此人）：4401 关闭，前端清 token 回登录页
        if (Boolean.TRUE.equals(browserSession.getAttributes().get(AuthHandshakeInterceptor.ATTR_USER_MISSING))) {
            log.warn("WS 拒绝幽灵用户: browser={}", browserSession.getId());
            browserSession.close(new CloseStatus(4401, "用户不存在"));
            return;
        }
        String token = (String) browserSession.getAttributes().get(AuthHandshakeInterceptor.ATTR_TOKEN);
        Long userId = (Long) browserSession.getAttributes().get(AuthHandshakeInterceptor.ATTR_USER_ID);
        URI engineUri = URI.create(engineWsBase + "/ws?token="
                + URLEncoder.encode(token, StandardCharsets.UTF_8));

        StandardWebSocketClient client = new StandardWebSocketClient(webSocketContainer);
        WebSocketSession engineSession;
        try {
            engineSession = client
                    .execute(new EngineToBrowserHandler(browserSession), new WebSocketHttpHeaders(), engineUri)
                    .get(ENGINE_CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (Exception e) {
            log.warn("连接引擎 WS 失败: userId={} uri={} error={}", userId, engineWsBase, e.getMessage());
            browserSession.close(CloseStatus.SERVICE_RESTARTED);
            return;
        }
        browserSession.getAttributes().put(ATTR_ENGINE_SESSION, engineSession);
        log.info("WS relay 已建立: userId={} browser={} engine={}",
                userId, browserSession.getId(), engineSession.getId());
    }

    @Override
    protected void handleTextMessage(WebSocketSession browserSession, TextMessage message) throws Exception {
        String payload = message.getPayload();
        if (tryHandleControlPlane(browserSession, payload)) {
            return;
        }
        WebSocketSession engineSession = engineSession(browserSession);
        if (engineSession != null && engineSession.isOpen()) {
            sendSafely(engineSession, payload);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession browserSession, CloseStatus status) throws Exception {
        turnStreamReader.closeFor(browserSession);
        WebSocketSession engineSession = engineSession(browserSession);
        if (engineSession != null && engineSession.isOpen()) {
            engineSession.close(status);
        }
        log.info("WS relay 已断开: browser={} status={}", browserSession.getId(), status);
    }

    @Override
    public void handleTransportError(WebSocketSession browserSession, Throwable exception) throws Exception {
        log.warn("浏览器 WS 传输错误: browser={} error={}", browserSession.getId(), exception.getMessage());
        if (browserSession.isOpen()) {
            browserSession.close(CloseStatus.SERVER_ERROR);
        }
    }

    /**
     * 拦截网关本地处理的请求帧，返回 true 表示已处理，不再透传：
     * - session/list、session/history：只读查询，网关本地查库合成应答
     * - turn/start、turn/cancel：转 MQ 消息；发布失败回退透传，
     *   业务拒绝（积分不足等）直接应答错误，不回退
     * - stream/subscribe：订阅事件流推送
     * 其余方法、响应帧（无 method）、解析失败的帧一律透传。
     */
    private boolean tryHandleControlPlane(WebSocketSession browserSession, String payload) throws IOException {
        JsonNode frame;
        try {
            frame = objectMapper.readTree(payload);
        } catch (Exception e) {
            return false;
        }
        JsonNode methodNode = frame.get("method");
        JsonNode idNode = frame.get("id");
        if (methodNode == null || !methodNode.isTextual() || idNode == null || idNode.isNull()) {
            return false;
        }
        String method = methodNode.asText();
        if ("session/list".equals(method) || "session/history".equals(method)) {
            Long userId = (Long) browserSession.getAttributes().get(AuthHandshakeInterceptor.ATTR_USER_ID);
            handleSessionQuery(browserSession, idNode, method, frame.get("params"), userId);
            return true;
        }
        if (!"turn/start".equals(method) && !"turn/cancel".equals(method)
                && !"stream/subscribe".equals(method)) {
            return false;
        }

        Long userId = (Long) browserSession.getAttributes().get(AuthHandshakeInterceptor.ATTR_USER_ID);
        JsonNode params = frame.get("params");
        JsonNode sessionIdNode = params == null ? null : params.get("sessionId");
        if (sessionIdNode == null || !sessionIdNode.isTextual() || sessionIdNode.asText().isBlank()) {
            sendRpcError(browserSession, idNode, INVALID_PARAMS, "缺少 sessionId");
            return true;
        }
        String sessionId = sessionIdNode.asText();

        if ("stream/subscribe".equals(method)) {
            JsonNode lastSeqNode = params.get("lastSeq");
            String lastSeq = lastSeqNode == null || lastSeqNode.isNull() ? null : lastSeqNode.asText();
            turnStreamReader.subscribe(browserSession, sessionId, lastSeq);
            sendRpcResult(browserSession, idNode);
            return true;
        }

        try {
            if ("turn/start".equals(method)) {
                JsonNode inputNode = params.get("input");
                String input = inputNode == null ? "" : inputNode.asText();
                long turnId = turnDispatchService.dispatch(userId, sessionId, input);
                log.info("turn 已派发 MQ: turnId={} sessionId={} userId={}", turnId, sessionId, userId);
            } else {
                turnDispatchService.cancel(userId, sessionId);
                log.info("turn 取消已派发 MQ: sessionId={} userId={}", sessionId, userId);
            }
        } catch (BizException e) {
            // 业务拒绝（如积分不足）：直接应答用户，不回退透传——透传会绕过派发侧控制
            sendRpcError(browserSession, idNode, BIZ_REJECTED, e.getMessage());
            return true;
        } catch (Exception e) {
            log.warn("MQ 发布失败，回退 WS 透传: method={} error={}", method, e.getMessage());
            return false;
        }
        sendRpcResult(browserSession, idNode);
        return true;
    }

    /**
     * 本地应答只读会话查询：session/list 按用户列出未删除会话，session/history
     * 归属校验后分页。
     */
    private void handleSessionQuery(WebSocketSession session, JsonNode idNode, String method, JsonNode params,
                                    Long userId) throws IOException {
        try {
            if ("session/list".equals(method)) {
                sendRpcResult(session, idNode, listSessions(userId, params));
                return;
            }
            JsonNode sessionIdNode = params == null ? null : params.get("sessionId");
            if (sessionIdNode == null || !sessionIdNode.isTextual() || sessionIdNode.asText().isBlank()) {
                sendRpcError(session, idNode, INVALID_PARAMS, "缺少 sessionId");
                return;
            }
            // 注意校验顺序：direction → limit → cursor，调整顺序会改变报错优先级
            String direction = readDirection(params);
            Integer limit = readLimit(params);
            String cursor = readCursor(params);
            ObjectNode result = sessionHistoryService.queryHistory(
                    sessionIdNode.asText(), userId, cursor, limit, direction);
            sendRpcResult(session, idNode, result);
        } catch (UnknownSessionException e) {
            sendRpcError(session, idNode, SessionHistoryService.SESSION_NOT_FOUND, e.getMessage());
        } catch (IllegalArgumentException e) {
            sendRpcError(session, idNode, INVALID_PARAMS, e.getMessage());
        } catch (Exception e) {
            log.warn("会话查询失败: method={} error={}", method, e.toString());
            sendRpcError(session, idNode, INTERNAL_ERROR, "会话查询失败");
        }
    }

    /** session/list 的 result；params 里带 workId 时只返回该 work 下的会话 */
    private ObjectNode listSessions(Long userId, JsonNode params) {
        JsonNode workIdNode = params == null ? null : params.get("workId");
        String workId = workIdNode != null && workIdNode.isTextual() && !workIdNode.asText().isBlank()
                ? workIdNode.asText() : null;
        ObjectNode result = objectMapper.createObjectNode();
        ArrayNode sessions = result.putArray("sessions");
        for (Session row : internalStoreService.listUserSessions(userId, workId)) {
            ObjectNode item = sessions.addObject();
            item.put("sessionId", row.getId());
            item.put("workId", row.getWorkId());
            item.put("title", row.getTitle());
            item.put("createdAt", TimeFormat.isoUtc(row.getCreatedAt()));
            item.put("updatedAt", TimeFormat.isoUtc(row.getUpdatedAt()));
        }
        return result;
    }

    private static String readCursor(JsonNode params) {
        JsonNode node = params.get("cursor");
        if (node == null || node.isNull()) {
            return null;
        }
        if (!node.isTextual()) {
            throw new IllegalArgumentException("invalid history cursor");
        }
        return node.asText();
    }

    /** limit 非整数按非法拒绝；缺失（null）表示返回完整历史；0/负数由分页核心拒绝 */
    private static Integer readLimit(JsonNode params) {
        JsonNode node = params.get("limit");
        if (node == null || node.isNull()) {
            return null;
        }
        if (!node.isIntegralNumber() || !node.canConvertToExactIntegral()) {
            throw new IllegalArgumentException("invalid history limit");
        }
        long value = node.asLong();
        return value > Integer.MAX_VALUE ? Integer.MAX_VALUE : (int) value;
    }

    private static String readDirection(JsonNode params) {
        JsonNode node = params.get("direction");
        if (node == null || node.isNull()) {
            return "forward";
        }
        if (!node.isTextual()) {
            throw new IllegalArgumentException("invalid history direction");
        }
        return node.asText();
    }

    /** 网关本地合成 JSON-RPC 成功应答（turn 提交语义：受理即返回，结果经事件流下发） */
    private void sendRpcResult(WebSocketSession session, JsonNode idNode) throws IOException {
        sendRpcResult(session, idNode, objectMapper.createObjectNode());
    }

    private void sendRpcResult(WebSocketSession session, JsonNode idNode, ObjectNode result) throws IOException {
        ObjectNode response = objectMapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", idNode);
        response.set("result", result);
        sendSafely(session, objectMapper.writeValueAsString(response));
    }

    private void sendRpcError(WebSocketSession session, JsonNode idNode, int code, String message)
            throws IOException {
        ObjectNode response = objectMapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", idNode);
        ObjectNode error = response.putObject("error");
        error.put("code", code);
        error.put("message", message);
        sendSafely(session, objectMapper.writeValueAsString(response));
    }

    private static WebSocketSession engineSession(WebSocketSession browserSession) {
        return (WebSocketSession) browserSession.getAttributes().get(ATTR_ENGINE_SESSION);
    }

    /**
     * WebSocketSession 的发送不是线程安全的（浏览器→引擎在 Tomcat 线程，
     * 引擎→浏览器在 client 容器线程），同一会话的发送必须串行
     */
    private static void sendSafely(WebSocketSession session, String payload) throws IOException {
        synchronized (session) {
            if (session.isOpen()) {
                session.sendMessage(new TextMessage(payload));
            }
        }
    }

    /**
     * 引擎方向的处理者：把引擎下发的帧转发回浏览器；引擎断开则联动断开浏览器连接
     */
    private static class EngineToBrowserHandler extends TextWebSocketHandler {

        private final WebSocketSession browserSession;

        EngineToBrowserHandler(WebSocketSession browserSession) {
            this.browserSession = browserSession;
        }

        @Override
        protected void handleTextMessage(WebSocketSession engineSession, TextMessage message) throws Exception {
            sendSafely(browserSession, message.getPayload());
        }

        @Override
        public void afterConnectionClosed(WebSocketSession engineSession, CloseStatus status) throws Exception {
            if (browserSession.isOpen()) {
                browserSession.close(status);
            }
        }

        @Override
        public void handleTransportError(WebSocketSession engineSession, Throwable exception) throws Exception {
            log.warn("引擎 WS 传输错误: engine={} error={}", engineSession.getId(), exception.getMessage());
        }
    }
}
