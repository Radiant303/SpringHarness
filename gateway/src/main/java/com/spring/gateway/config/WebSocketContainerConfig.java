package com.spring.gateway.config;

import jakarta.websocket.ContainerProvider;
import jakarta.websocket.WebSocketContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * WS 容器缓冲配置。独立成类以避免循环依赖。
 *
 * <p>Tomcat 单帧缓冲默认 8192 字节，大载荷消息超出即被对端以 1009 关闭连接，
 * 故调大单帧上限。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Configuration
public class WebSocketContainerConfig {

    /** WS 单帧大小上限：16MB */
    private static final int MAX_WS_MESSAGE_BYTES = 16 * 1024 * 1024;

    @Bean
    public WebSocketContainer webSocketContainer() {
        WebSocketContainer container = ContainerProvider.getWebSocketContainer();
        container.setDefaultMaxTextMessageBufferSize(MAX_WS_MESSAGE_BYTES);
        container.setDefaultMaxBinaryMessageBufferSize(MAX_WS_MESSAGE_BYTES);
        return container;
    }
}
