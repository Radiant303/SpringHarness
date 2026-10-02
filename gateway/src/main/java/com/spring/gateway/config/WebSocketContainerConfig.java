package com.spring.gateway.config;

import jakarta.websocket.ContainerProvider;
import jakarta.websocket.WebSocketContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * WS 容器缓冲配置（独立成类是为了避免循环依赖：
 * WebSocketConfig → EngineRelayHandler → webSocketContainer）。
 *
 * <p>Tomcat 单帧缓冲默认 8192 字节，引擎的 initialize 应答、会话列表等载荷
 * 远超这个值，超出即被对端以 1009 关闭连接。网关到引擎的 WS 客户端与浏览器
 * 到网关的服务端共用 ContainerProvider 的这个共享容器，一起调大。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Configuration
public class WebSocketContainerConfig {

    /** 与引擎侧 uvicorn 的 ws_max_size 默认值（16MB）对齐，网关不当瓶颈 */
    private static final int MAX_WS_MESSAGE_BYTES = 16 * 1024 * 1024;

    @Bean
    public WebSocketContainer webSocketContainer() {
        WebSocketContainer container = ContainerProvider.getWebSocketContainer();
        container.setDefaultMaxTextMessageBufferSize(MAX_WS_MESSAGE_BYTES);
        container.setDefaultMaxBinaryMessageBufferSize(MAX_WS_MESSAGE_BYTES);
        return container;
    }
}
