package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 管理后台的用户列表行。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param userId         用户 ID（字符串：雪花 ID 超 2^53，JS 数字会丢精度）
 * @param username       用户名
 * @param role           角色（owner/admin/user）
 * @param status         账号状态（active/disabled）
 * @param quotaBytes     存储配额（字节）
 * @param workQuotaBytes 单工作区上限覆盖值（字节，null 跟随全局）
 * @param createdAt      注册时间（ISO UTC）
 */
public record AdminUserView(
        @JsonProperty("user_id") String userId,
        String username,
        String role,
        String status,
        @JsonProperty("quota_bytes") Long quotaBytes,
        @JsonProperty("work_quota_bytes") Long workQuotaBytes,
        @JsonProperty("created_at") String createdAt
) {
}
