package com.spring.gateway.config;

import com.spring.gateway.common.AuthInterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web MVC 配置。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Configuration
@RequiredArgsConstructor
public class WebConfig implements WebMvcConfigurer {

    private final AuthInterceptor authInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor).addPathPatterns("/api/sessions/**");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        // 前端 HTML 以 /static/ 前缀引用静态资源，保持该前缀兼容
        registry.addResourceHandler("/static/**").addResourceLocations("file:../frontend/");
    }
}
