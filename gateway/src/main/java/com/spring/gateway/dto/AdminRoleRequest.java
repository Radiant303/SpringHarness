package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * 任命/罢免管理员请求。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param role 目标角色（admin/user；owner 不可经 API 授予）
 */
public record AdminRoleRequest(
        @NotBlank @Pattern(regexp = "admin|user", message = "role 只能是 admin 或 user")
        String role
) {
}
