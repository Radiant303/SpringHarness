package com.spring.gateway.controller;

import com.spring.gateway.common.Result;
import com.spring.gateway.service.MqMonitor;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * MQ 运维查询接口（鉴权由 AuthInterceptor 对 /api/admin/** 生效）。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@RestController
@RequestMapping("/api/admin/mq")
@RequiredArgsConstructor
public class MqAdminController {

    private final MqMonitor mqMonitor;

    /**
     * 各队列当前堆积量（含死信队列）
     *
     * @return 队列名 → 堆积消息数（队列为 null 表示尚未声明）
     */
    @GetMapping("/queues")
    public Result<Map<String, Long>> queues() {
        return Result.ok(mqMonitor.queueDepths());
    }
}
