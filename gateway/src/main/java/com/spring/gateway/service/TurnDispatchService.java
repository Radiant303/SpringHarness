package com.spring.gateway.service;

import com.spring.gateway.common.BizException;
import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.config.RabbitConfig;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * turn 派发：把拦下的 turn/start、turn/cancel 转为 MQ 消息。
 *
 * <p>turnId 为雪花 ID，同时是消费端的幂等键。
 * turn/start 发布前先完成积分预扣（余额不足当场抛 409，不消耗引擎资源）；
 * 发布同步等待 broker 确认，失败先补偿释放预扣再抛异常由调用方处理。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TurnDispatchService {

    /** 同步确认超时：超过视为发布失败 */
    private static final long CONFIRM_TIMEOUT_MS = 5000;

    private final RabbitTemplate rabbitTemplate;
    private final SnowflakeIdGenerator idGenerator;
    private final BillingService billingService;

    /**
     * 派发一轮对话
     *
     * @param userId    用户 ID
     * @param sessionId 会话 ID
     * @param input     用户输入
     * @return turnId（雪花 ID，消费端幂等键）
     * @throws BizException 积分不足（409），调用方应直接应答用户而非回退
     */
    public long dispatch(long userId, String sessionId, String input) {
        long turnId = idGenerator.nextId();
        billingService.preDeduct(userId, String.valueOf(turnId));
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("turnId", turnId);
        message.put("sessionId", sessionId);
        message.put("userId", userId);
        message.put("input", input);
        message.put("enqueuedAt", Instant.now().toString());
        try {
            publish(RabbitConfig.QUEUE_DISPATCH, message);
        } catch (Exception e) {
            // 发布失败：补偿释放预扣（尽力而为），调用方按原路径回退透传
            try {
                billingService.releaseHold(String.valueOf(turnId));
            } catch (Exception releaseError) {
                log.error("预扣补偿释放失败（过期扫描兜底）: turnId={} error={}",
                        turnId, releaseError.toString());
            }
            throw e;
        }
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
        publish(RabbitConfig.QUEUE_CANCEL, message);
    }

    /** 发送并同步等待 broker 确认；确认失败/超时抛 AmqpException，由调用方决定回退 */
    private void publish(String routingKey, Map<String, Object> message) {
        rabbitTemplate.invoke(template -> {
            template.convertAndSend(RabbitConfig.TURN_EXCHANGE, routingKey, message);
            template.waitForConfirmsOrDie(CONFIRM_TIMEOUT_MS);
            return null;
        });
    }
}
