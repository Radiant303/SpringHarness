package com.spring.gateway.dto;

import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.entity.Session;

/**
 * 会话摘要（网关内部线格式）。字段命名与 Python 侧 schemas.SessionSummary 一致：
 * 内部 API 用驼峰风格，REST /api/sessions 用下划线风格，两处都是跨服务契约。
 * <p>时间戳为 naive UTC，序列化成 ISO + "Z"；userId 供调用方复核归属。</p>
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
