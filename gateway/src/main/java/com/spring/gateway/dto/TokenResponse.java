package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 登录成功返回体，user_id 为蛇形命名。
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
