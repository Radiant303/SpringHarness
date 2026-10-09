package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * 管理后台的模型定义行。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param id             模型 ID
 * @param provider       所属 Provider
 * @param model          实际模型名
 * @param displayName    展示名
 * @param maxContextSize 上下文窗口（tokens）
 * @param maxOutputSize  输出上限（tokens）
 * @param capabilities   能力列表
 * @param supportEfforts 支持的思考档位
 * @param defaultEffort  默认思考档位
 * @param reasoningKey   推理内容字段名
 * @param enabled        是否启用
 * @param isDefault      是否默认模型
 * @param updatedAt      更新时间（ISO UTC）
 */
public record AdminModelDefView(
        String id,
        String provider,
        String model,
        @JsonProperty("display_name") String displayName,
        @JsonProperty("max_context_size") Long maxContextSize,
        @JsonProperty("max_output_size") Long maxOutputSize,
        List<String> capabilities,
        @JsonProperty("support_efforts") List<String> supportEfforts,
        @JsonProperty("default_effort") String defaultEffort,
        @JsonProperty("reasoning_key") String reasoningKey,
        Boolean enabled,
        @JsonProperty("is_default") boolean isDefault,
        @JsonProperty("updated_at") String updatedAt
) {
}
