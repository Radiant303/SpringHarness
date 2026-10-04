package com.spring.gateway.common;

/**
 * 会话不存在、不属于当前用户或已删除。与 Python 侧 engine 的
 * {@code JsonRpcError(SESSION_NOT_FOUND, f"未知会话: {session_id}")} 语义一致：
 * 不区分"不存在"与"越权"两种失败，以防 IDOR 探测。
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
