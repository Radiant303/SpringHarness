package com.spring.gateway.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.web.client.RestClient;

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

    /**
     * 注册指向 Python 引擎的 RestClient
     *
     * @param baseUrl 引擎基础地址（配置项 app.engine-base-url）
     * @return 引擎 RestClient
     */
    @Bean
    public RestClient engineRestClient(@Value("${app.engine-base-url}") String baseUrl) {
        return RestClient.builder().baseUrl(baseUrl).build();
    }
}
