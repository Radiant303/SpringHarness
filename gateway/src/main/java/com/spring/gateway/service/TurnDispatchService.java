package com.spring.gateway.service;

import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.config.RabbitConfig;
import lombok.RequiredArgsConstructor;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * turn 控制面派发：把 WS 上拦下的 turn/start、turn/cancel 转为 MQ 消息。
 *
 * <p>turnId 为雪花 ID，同时是 Python 消费端的幂等键。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Service
@RequiredArgsConstructor
public class TurnDispatchService {

    private final RabbitTemplate rabbitTemplate;
    private final SnowflakeIdGenerator idGenerator;

    /**
     * 派发一轮对话
     *
     * @param userId    用户 ID
     * @param sessionId 会话 ID
     * @param input     用户输入
     * @return turnId（雪花 ID，消费端幂等键）
     */
    public long dispatch(long userId, String sessionId, String input) {
        long turnId = idGenerator.nextId();
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("turnId", turnId);
        message.put("sessionId", sessionId);
        message.put("userId", userId);
        message.put("input", input);
        message.put("enqueuedAt", Instant.now().toString());
        rabbitTemplate.convertAndSend(RabbitConfig.TURN_EXCHANGE, RabbitConfig.QUEUE_DISPATCH, message);
        return turnId;
    }

    /**
     * 取消某会话当前轮次（按会话寻址：同会话串行，任一时刻只有一个活跃 turn）
     *
     * @param userId    用户 ID
     * @param sessionId 会话 ID
     */
    public void cancel(long userId, String sessionId) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("sessionId", sessionId);
        message.put("userId", userId);
        message.put("enqueuedAt", Instant.now().toString());
        rabbitTemplate.convertAndSend(RabbitConfig.TURN_EXCHANGE, RabbitConfig.QUEUE_CANCEL, message);
    }
}
