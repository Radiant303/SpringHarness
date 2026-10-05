package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.entity.PointsHold;
import com.spring.gateway.mapper.PointsHoldMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

/**
 * 在途预扣的过期扫描：引擎崩溃等导致 lifecycle 事件永远不到达时，
 * 超时预扣由这里兜底释放退回，积分不悬挂。
 *
 * <p>独立成 bean：逐笔调 BillingService.releaseHold（各自独立事务），
 * 避免自调用丢事务；单笔失败不拖累其余。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HoldExpirySweeper {

    /** 在途超过该时长视为悬挂（一轮对话的正常时长远低于此）。 */
    private static final long EXPIRE_MINUTES = 10;

    /** 单轮扫描处理上限，防 backlog 时长尾。 */
    private static final int BATCH_LIMIT = 100;

    private final PointsHoldMapper pointsHoldMapper;
    private final BillingService billingService;

    @Scheduled(fixedDelay = 60_000, initialDelay = 60_000)
    public void sweep() {
        List<PointsHold> stale = pointsHoldMapper.selectList(new LambdaQueryWrapper<PointsHold>()
                .eq(PointsHold::getStatus, PointsHold.STATUS_HELD)
                .lt(PointsHold::getCreatedAt,
                        LocalDateTime.now(ZoneOffset.UTC).minusMinutes(EXPIRE_MINUTES))
                .last("LIMIT " + BATCH_LIMIT));
        for (PointsHold hold : stale) {
            try {
                billingService.releaseHold(hold.getTurnId());
                log.info("过期预扣已释放: turnId={} userId={} amount={}",
                        hold.getTurnId(), hold.getUserId(), hold.getAmount());
            } catch (Exception e) {
                log.error("过期预扣释放失败: turnId={} error={}", hold.getTurnId(), e.toString());
            }
        }
    }
}
