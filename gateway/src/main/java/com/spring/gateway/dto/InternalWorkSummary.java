package com.spring.gateway.dto;

import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.entity.Work;

/**
 * work 摘要。workspacePath 由网关按 {data-root}/works/{workId} 派生，路径权威在网关一侧。
 *
 * @author hanbing
 * @since 2026-10-04
 * @param workId        work ID
 * @param userId        所属用户 ID
 * @param name          项目名
 * @param sizeBytes     目录当前占用字节数
 * @param defaultWork   是否默认项目
 * @param workspacePath 派生的工作区目录路径
 * @param createdAt     创建时间
 * @param updatedAt     更新时间
 */
public record InternalWorkSummary(
        String workId,
        Long userId,
        String name,
        long sizeBytes,
        boolean defaultWork,
        String workspacePath,
        String createdAt,
        String updatedAt
) {

    /**
     * 由 works 行构造摘要
     *
     * @param row           works 行
     * @param workspacePath 网关派生的工作区目录路径
     * @return work 摘要
     */
    public static InternalWorkSummary from(Work row, String workspacePath) {
        return new InternalWorkSummary(
                row.getId(),
                row.getUserId(),
                row.getName(),
                row.getSizeBytes() == null ? 0L : row.getSizeBytes(),
                Boolean.TRUE.equals(row.getIsDefault()),
                workspacePath,
                TimeFormat.isoUtc(row.getCreatedAt()),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }
}
