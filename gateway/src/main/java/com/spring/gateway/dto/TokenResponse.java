package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 登录成功返回体。user_id 字段保持蛇形命名，与 Python 侧响应结构一致。
 *
 * @author hanbing
 * @since 2026-09-26
 * @param token    JWT
 * @param userId   用户 ID
 * @param username 用户名
 */
public record TokenResponse(
        String token,
        @JsonProperty("user_id") Long userId,
        String username
) {
}
