package com.spring.gateway.dto;

import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.entity.Session;

/**
 * 会话摘要。时间戳序列化为 ISO 格式并补 Z 后缀。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param sessionId      会话 ID
 * @param userId         所属用户 ID
 * @param title          会话标题，取首条用户消息的截断文本
 * @param workspacePath  工作区目录路径
 * @param currentSegment 当前段号
 * @param status         状态：active / deleted
 * @param createdAt      创建时间
 * @param updatedAt      更新时间
 */
public record InternalSessionSummary(
        String sessionId,
        Long userId,
        String title,
        String workspacePath,
        Integer currentSegment,
        String status,
        String createdAt,
        String updatedAt
) {

    /**
     * 由 sessions 行构造摘要
     *
     * @param row sessions 行
     * @return 会话摘要
     */
    public static InternalSessionSummary from(Session row) {
        return new InternalSessionSummary(
                row.getId(),
                row.getUserId(),
                row.getTitle(),
                row.getWorkspacePath(),
                row.getCurrentSegment(),
                row.getStatus(),
                TimeFormat.isoUtc(row.getCreatedAt()),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }
}
