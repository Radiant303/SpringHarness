package com.spring.gateway.common;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 统一返回体。
 *
 * @param <T> 业务数据类型
 * @author hanbing
 * @since 2026-09-26
 */
@Data
@AllArgsConstructor
@NoArgsConstructor
public class Result<T> {

    /**
     * 状态码
     */
    private int code;

    /**
     * 提示信息
     */
    private String message;

    /**
     * 业务数据
     */
    private T data;

    /**
     * 构造成功返回体
     *
     * @param data 业务数据
     * @param <T>  业务数据类型
     * @return code 为 200 的返回体
     */
    public static <T> Result<T> ok(T data) {
        return new Result<>(200, "ok", data);
    }

    /**
     * 构造失败返回体
     *
     * @param code    错误码（复用 HTTP 状态码）
     * @param message 错误描述
     * @return 无业务数据的返回体
     */
    public static Result<Void> error(int code, String message) {
        return new Result<>(code, message, null);
    }
}
