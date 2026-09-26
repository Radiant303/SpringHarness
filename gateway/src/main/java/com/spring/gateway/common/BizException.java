package com.spring.gateway.common;

import lombok.Getter;

/**
 * 业务异常。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Getter
public class BizException extends RuntimeException {

    /**
     * 状态码
     */
    private final int status;

    /**
     * @param status  HTTP 状态码
     * @param message 错误描述
     */
    public BizException(int status, String message) {
        super(message);
        this.status = status;
    }
}
