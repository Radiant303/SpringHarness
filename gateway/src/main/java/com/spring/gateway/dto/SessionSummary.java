package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.LocalDateTime;

/**
 * 会话摘要。时间戳序列化时补 Z 后缀标明时区。
 *
 * @author hanbing
 * @since 2026-09-26
 * @param sessionId 会话 ID
 * @param workId    所属 work ID
 * @param title     会话标题
 * @param createdAt 创建时间
 * @param updatedAt 更新时间
 */
public record SessionSummary(
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("work_id") String workId,
        String title,
        @JsonProperty("created_at")
        @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'", timezone = "UTC") LocalDateTime createdAt,
        @JsonProperty("updated_at")
        @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'", timezone = "UTC") LocalDateTime updatedAt
) {
}
