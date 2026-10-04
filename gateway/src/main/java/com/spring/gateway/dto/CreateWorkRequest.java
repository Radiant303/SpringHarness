package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 新建 work 请求。
 *
 * @author hanbing
 * @since 2026-10-04
 * @param name 项目名，长度 1~128
 */
public record CreateWorkRequest(
        @NotBlank(message = "项目名不能为空")
        @Size(max = 128, message = "项目名最长 128 字")
        String name
) {
}
