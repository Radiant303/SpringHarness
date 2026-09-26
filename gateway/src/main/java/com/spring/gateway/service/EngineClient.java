package com.spring.gateway.service;

import com.spring.gateway.common.BizException;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.Optional;
import java.util.function.Supplier;

/**
 * Python 引擎客户端，封装会话写接口与历史接口的转发。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Component
@RequiredArgsConstructor
public class EngineClient {

    private final RestClient engineRestClient;
    private final ObjectMapper objectMapper;

    /**
     * 新建会话
     *
     * @param authorization 原始 Authorization 头，原样透传给引擎验签
     * @return 引擎返回的会话摘要
     */
    public JsonNode createSession(String authorization) {
        return call(() -> engineRestClient.post()
                .uri("/api/sessions")
                .header(HttpHeaders.AUTHORIZATION, authorization)
                .retrieve()
                .body(JsonNode.class));
    }

    /**
     * 删除会话
     *
     * @param sessionId     会话 ID
     * @param authorization 原始 Authorization 头
     */
    public void deleteSession(String sessionId, String authorization) {
        call(() -> engineRestClient.delete()
                .uri("/api/sessions/{sessionId}", sessionId)
                .header(HttpHeaders.AUTHORIZATION, authorization)
                .retrieve()
                .toBodilessEntity());
    }

    /**
     * 查询会话历史分页
     *
     * @param sessionId     会话 ID
     * @param cursor        分页游标，可为 null
     * @param limit         每页消息数
     * @param direction     翻页方向：forward / backward
     * @param authorization 原始 Authorization 头
     * @return 引擎返回的历史分页
     */
    public JsonNode history(String sessionId, String cursor, int limit, String direction,
                            String authorization) {
        return call(() -> engineRestClient.get()
                .uri(builder -> builder
                        .path("/api/sessions/{sessionId}/history")
                        .queryParam("limit", limit)
                        .queryParam("direction", direction)
                        .queryParamIfPresent("cursor", Optional.ofNullable(cursor))
                        .build(sessionId))
                .header(HttpHeaders.AUTHORIZATION, authorization)
                .retrieve()
                .body(JsonNode.class));
    }

    /**
     * 执行引擎调用并统一翻译异常：引擎 4xx 透传状态码与 detail，引擎 5xx 与连接失败归为 502
     */
    private <T> T call(Supplier<T> supplier) {
        try {
            return supplier.get();
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().is5xxServerError()) {
                throw new BizException(502, "引擎内部错误");
            }
            throw new BizException(e.getStatusCode().value(), extractDetail(e));
        } catch (ResourceAccessException e) {
            throw new BizException(502, "引擎服务不可用");
        }
    }

    /**
     * 从引擎错误响应体中提取 detail 字段
     */
    private String extractDetail(RestClientResponseException e) {
        try {
            JsonNode detail = objectMapper.readTree(e.getResponseBodyAsString()).get("detail");
            if (detail != null && detail.isTextual()) {
                return detail.asText();
            }
        } catch (Exception ignored) {
            // 响应体不是预期 JSON 时使用默认描述
        }
        return "引擎返回错误";
    }
}
