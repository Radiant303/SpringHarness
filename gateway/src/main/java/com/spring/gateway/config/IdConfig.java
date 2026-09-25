package com.spring.gateway.config;

import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.common.WorkerIdAllocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IdConfig {

    @Bean
    public SnowflakeIdGenerator snowflakeIdGenerator(WorkerIdAllocator allocator) {
        return new SnowflakeIdGenerator(allocator.getWorkerId());
    }
}
