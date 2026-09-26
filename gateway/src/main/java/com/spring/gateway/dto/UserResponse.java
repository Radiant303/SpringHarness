package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 注册成功返回体。字段命名与 Python 侧响应结构一致。
 *
 * @author hanbing
 * @since 2026-09-26
 * @param userId   用户 ID
 * @param username 用户名
 */
public record UserResponse(
        @JsonProperty("user_id") Long userId,
        String username
) {
}
