package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * work 摘要。sizeBytes 为目录当前占用字节数，defaultWork 标识默认项目。
 *
 * @author hanbing
 * @since 2026-10-04
 * @param workId      work ID
 * @param name        项目名
 * @param sizeBytes   目录当前占用字节数
 * @param defaultWork 是否默认项目
 * @param createdAt   创建时间
 * @param updatedAt   更新时间
 */
public record WorkSummary(
        @JsonProperty("work_id") String workId,
        String name,
        @JsonProperty("size_bytes") long sizeBytes,
        @JsonProperty("default_work") boolean defaultWork,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("updated_at") String updatedAt
) {
}
