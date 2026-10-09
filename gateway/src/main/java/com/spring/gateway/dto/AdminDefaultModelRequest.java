package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * 设置默认模型请求。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param modelId 模型 ID（必须已存在且启用）
 */
public record AdminDefaultModelRequest(
        @NotBlank(message = "模型 ID 不能为空")
        String modelId
) {
}
