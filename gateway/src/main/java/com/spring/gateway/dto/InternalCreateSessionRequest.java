package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * 内部接口：新建会话请求，会话落在指定 work 的工作区目录下。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param sessionId 会话 ID（UUID 字符串）
 * @param userId    所属用户 ID
 * @param workId    所属 work ID
 */
public record InternalCreateSessionRequest(
        @NotBlank(message = "sessionId 不能为空")
        String sessionId,

        @NotNull(message = "userId 不能为空")
        Long userId,

        @NotBlank(message = "workId 不能为空")
        String workId
) {
}
