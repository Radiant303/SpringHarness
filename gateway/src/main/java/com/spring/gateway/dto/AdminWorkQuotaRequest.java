package com.spring.gateway.dto;

import jakarta.validation.constraints.Min;

/**
 * 调整用户单工作区上限覆盖值请求；null 表示恢复跟随全局设置。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param quotaBytes 覆盖值（字节，0 表示不允许写入），null 恢复跟随全局
 */
public record AdminWorkQuotaRequest(
        @Min(value = 0, message = "上限不能为负")
        Long quotaBytes
) {
}
