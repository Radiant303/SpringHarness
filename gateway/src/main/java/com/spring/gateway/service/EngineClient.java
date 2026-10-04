package com.spring.gateway.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.JsonNode;

/**
 * 引擎 HTTP 客户端：仅承载网关需要反向询问引擎的少量端点（如 work 活跃会话数）。
 *
 * @author hanbing
 * @since 2026-10-04
 */
@Component
public class EngineClient {

    private final RestClient restClient;

    public EngineClient(@Value("${app.engine-base-url}") String engineBaseUrl,
                        @Value("${app.internal-token}") String internalToken) {
        this.restClient = RestClient.builder()
                .baseUrl(engineBaseUrl)
                .defaultHeader("X-Internal-Token", internalToken)
                .build();
    }

    /**
     * 查询引擎进程内某 work 的活跃会话数
     *
     * @param workId work ID
     * @return 活跃会话数
     */
    public int activeSessionsInWork(String workId) {
        JsonNode body = restClient.get()
                .uri("/internal/works/{workId}/active-sessions", workId)
                .retrieve()
                .body(JsonNode.class);
        return body == null ? 0 : body.get("active").asInt();
    }
}
