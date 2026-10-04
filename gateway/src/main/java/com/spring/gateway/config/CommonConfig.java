package com.spring.gateway.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/**
 * 通用装配配置。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Configuration
public class CommonConfig {

    /**
     * 注册 BCrypt 密码编码器
     *
     * @return BCrypt 密码编码器
     */
    @Bean
    public BCryptPasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
