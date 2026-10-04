package com.spring.gateway.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/**
 * 内部接口：work 目录大小上报请求。
 *
 * @author hanbing
 * @since 2026-10-04
 * @param sizeBytes 目录当前占用字节数
 */
public record InternalReportWorkSizeRequest(
        @NotNull(message = "sizeBytes 不能为空")
        @Min(0)
        Long sizeBytes
) {
}
