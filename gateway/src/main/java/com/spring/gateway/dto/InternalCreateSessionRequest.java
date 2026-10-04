package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * 内部 API：新建会话请求。会话 ID 由调用方（Python 引擎）生成并写入工作区路径。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param sessionId     会话 ID（UUID 字符串）
 * @param userId        所属用户 ID
 * @param workspacePath 工作区目录路径
 */
public record InternalCreateSessionRequest(
        @NotBlank(message = "sessionId 不能为空")
        String sessionId,

        @NotNull(message = "userId 不能为空")
        Long userId,

        @NotBlank(message = "workspacePath 不能为空")
        String workspacePath
) {
}
