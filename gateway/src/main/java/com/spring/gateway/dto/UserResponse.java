package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 注册成功返回体。
 *
 * @author hanbing
 * @since 2026-09-26
 * @param userId   用户 ID（字符串：雪花 ID 超 2^53，JS 数字会丢精度）
 * @param username 用户名
 */
public record UserResponse(
        @JsonProperty("user_id") String userId,
        String username
) {
}
