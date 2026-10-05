package com.spring.gateway.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/**
 * 调整全局单工作区上限请求（仅站长）。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param bytes 上限（字节，至少 1）
 */
public record AdminWorkMaxBytesRequest(
        @NotNull @Min(value = 1, message = "上限至少 1 字节")
        Long bytes
) {
}
