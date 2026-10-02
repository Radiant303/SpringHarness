package com.spring.gateway.config;

import com.spring.gateway.ws.AuthHandshakeInterceptor;
import com.spring.gateway.ws.EngineRelayHandler;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WS 接入配置：/ws 为聊天中继端点，握手时经 AuthHandshakeInterceptor 验 JWT。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Configuration
@EnableWebSocket
@RequiredArgsConstructor
public class WebSocketConfig implements WebSocketConfigurer {

    private final EngineRelayHandler engineRelayHandler;
    private final AuthHandshakeInterceptor authHandshakeInterceptor;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(engineRelayHandler, "/ws")
                .addInterceptors(authHandshakeInterceptor)
                // 开发期放开跨域；token 走 query 参数，鉴权不依赖同源
                .setAllowedOrigins("*");
    }
}
