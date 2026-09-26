package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.LocalDateTime;

/**
 * 会话摘要。字段命名与 Python 侧响应结构一致，存在跨服务契约，修改需两侧同步。
 * <p>时间戳存储为 naive UTC，序列化补 "Z" 后缀标明时区。</p>
 *
 * @author hanbing
 * @since 2026-09-26
 * @param sessionId 会话 ID
 * @param title     会话标题
 * @param createdAt 创建时间
 * @param updatedAt 更新时间
 */
public record SessionSummary(
        @JsonProperty("session_id") String sessionId,
        String title,
        @JsonProperty("created_at")
        @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'", timezone = "UTC") LocalDateTime createdAt,
        @JsonProperty("updated_at")
        @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'", timezone = "UTC") LocalDateTime updatedAt
) {
}
