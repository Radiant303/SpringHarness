package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 管理后台的 Provider 行；api_key 敏感不回值，只回 apiKeyConfigured。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param name             Provider 名
 * @param type             类型
 * @param baseUrl          自定义 base_url（null = 官方默认）
 * @param apiKeyConfigured 是否已配置 API Key
 * @param updatedAt        更新时间（ISO UTC）
 */
public record AdminProviderView(
        String name,
        String type,
        @JsonProperty("base_url") String baseUrl,
        @JsonProperty("api_key_configured") boolean apiKeyConfigured,
        @JsonProperty("updated_at") String updatedAt
) {
}
