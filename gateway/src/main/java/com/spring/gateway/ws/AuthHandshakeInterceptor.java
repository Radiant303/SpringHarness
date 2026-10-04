package com.spring.gateway.ws;

import com.spring.gateway.common.JwtUtils;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.util.Map;

/**
 * WS 握手鉴权：从 query 参数取 token 并验签，
 * 通过后把用户 ID 与原始 token 存入会话属性。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Component
@RequiredArgsConstructor
public class AuthHandshakeInterceptor implements HandshakeInterceptor {

    /** 握手成功后写入会话属性的键：用户 ID */
    public static final String ATTR_USER_ID = "userId";
    /** 握手成功后写入会话属性的键：原始 JWT */
    public static final String ATTR_TOKEN = "token";

    private final JwtUtils jwtUtils;

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                   WebSocketHandler wsHandler, Map<String, Object> attributes) {
        if (request instanceof ServletServerHttpRequest servletRequest) {
            String token = servletRequest.getServletRequest().getParameter("token");
            Long userId = token == null ? null : jwtUtils.parseUserId(token);
            if (userId != null) {
                attributes.put(ATTR_USER_ID, userId);
                attributes.put(ATTR_TOKEN, token);
                return true;
            }
        }
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        return false;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                               WebSocketHandler wsHandler, Exception exception) {
        // 无需后置处理
    }
}
