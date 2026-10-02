package com.spring.gateway.ws;

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
import tools.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/**
 * 聊天 WS 中继：浏览器 ↔ 网关 ↔ Python 引擎。
 *
 * <p>每条浏览器连接建立一条到引擎 /ws 的客户端连接，文本帧双向透传；
 * token 由握手拦截器校验后原样透传给引擎（引擎侧再做一次验签）。
 *
 * <p>控制面（阶段④）：turn/start、turn/cancel 请求帧不透传，转为 MQ 消息
 * （turn.dispatch / turn.cancel），网关本地合成 JSON-RPC 应答；token 流仍由
 * 引擎经既有 WS 泵推回。MQ 发布失败时回退为透传，由引擎 RPC 路由兜底。
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

    private final String engineWsBase;
    private final ObjectMapper objectMapper;
    private final TurnDispatchService turnDispatchService;
    private final TurnStreamReader turnStreamReader;
    private final WebSocketContainer webSocketContainer;

    public EngineRelayHandler(@Value("${app.engine-base-url}") String engineBaseUrl,
                              ObjectMapper objectMapper,
                              TurnDispatchService turnDispatchService,
                              TurnStreamReader turnStreamReader,
                              WebSocketContainer webSocketContainer) {
        // http(s)://host:port → ws(s)://host:port
        this.engineWsBase = engineBaseUrl.replaceFirst("^http", "ws");
        this.objectMapper = objectMapper;
        this.turnDispatchService = turnDispatchService;
        this.turnStreamReader = turnStreamReader;
        this.webSocketContainer = webSocketContainer;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession browserSession) throws Exception {
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
     * - turn/start、turn/cancel：控制面转 MQ（阶段④）；MQ 发布失败回退透传
     * - stream/subscribe：数据面订阅 Redis Stream（阶段⑤），由 TurnStreamReader 推送
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
        if (!"turn/start".equals(method) && !"turn/cancel".equals(method)
                && !"stream/subscribe".equals(method)) {
            return false;
        }

        Long userId = (Long) browserSession.getAttributes().get(AuthHandshakeInterceptor.ATTR_USER_ID);
        JsonNode params = frame.get("params");
        JsonNode sessionIdNode = params == null ? null : params.get("sessionId");
        if (sessionIdNode == null || !sessionIdNode.isTextual() || sessionIdNode.asText().isBlank()) {
            sendRpcError(browserSession, idNode, -32602, "缺少 sessionId");
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
        } catch (Exception e) {
            log.warn("MQ 发布失败，回退 WS 透传: method={} error={}", method, e.getMessage());
            return false;
        }
        sendRpcResult(browserSession, idNode);
        return true;
    }

    /** 网关本地合成 JSON-RPC 成功应答（turn 提交语义：受理即返回，结果经事件流下发） */
    private void sendRpcResult(WebSocketSession session, JsonNode idNode) throws IOException {
        ObjectNode response = objectMapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", idNode);
        response.putObject("result");
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
            if (browserSession.isOpen()) {
                browserSession.close(CloseStatus.SERVER_ERROR);
            }
        }
    }
}
