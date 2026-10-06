package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 用户兑换请求。输入允许带连字符/空格/小写，服务层规范化。
 *
 * @author hanbing
 * @since 2026-10-06
 * @param code 兑换码
 */
public record RedeemRequest(
        @NotBlank @Size(max = 64) String code
) {
}
