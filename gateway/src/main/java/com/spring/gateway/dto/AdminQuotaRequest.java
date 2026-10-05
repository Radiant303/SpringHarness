package com.spring.gateway.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/**
 * 调整存储配额请求。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param quotaBytes 配额（字节，0 表示不允许占用存储）
 */
public record AdminQuotaRequest(
        @NotNull @Min(value = 0, message = "配额不能为负")
        Long quotaBytes
) {
}
