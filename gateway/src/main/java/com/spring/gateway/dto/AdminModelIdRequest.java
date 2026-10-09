package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * 仅携带模型 ID 的请求（删除模型定义等）。id 含斜杠，必须放请求体而非路径变量。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param modelId 模型 ID
 */
public record AdminModelIdRequest(
        @NotBlank(message = "模型 ID 不能为空")
        String modelId
) {
}
