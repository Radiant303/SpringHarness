package com.spring.gateway.config;

import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.common.WorkerIdAllocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * ID 生成器装配配置。
 *
 * @author hanbing
 * @since 2026-09-25
 */
@Configuration
public class IdConfig {

    /**
     * 注册全局单例的雪花 ID 生成器
     *
     * @param allocator workerId 分配器
     * @return 雪花 ID 生成器
     */
    @Bean
    public SnowflakeIdGenerator snowflakeIdGenerator(WorkerIdAllocator allocator) {
        return new SnowflakeIdGenerator(allocator.getWorkerId());
    }
}
