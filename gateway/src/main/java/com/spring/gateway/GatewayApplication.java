package com.spring.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 网关启动类。负责用户认证、会话 API 与引擎转发。
 *
 * @author hanbing
 * @since 2026-09-25
 */
@SpringBootApplication
public class GatewayApplication {

    /**
     * 应用入口
     *
     * @param args 启动参数
     */
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }

}
