package com.spring.gateway.common;

/**
 * 未知会话异常：会话不存在、不属于当前用户或已删除时抛出；
 * 两种情况统一报错，避免通过报错差异探测会话 ID。
 *
 * @author hanbing
 * @since 2026-10-03
 */
public class UnknownSessionException extends RuntimeException {

    /**
     * @param sessionId 会话 ID
     */
    public UnknownSessionException(String sessionId) {
        super("未知会话: " + sessionId);
    }
}
