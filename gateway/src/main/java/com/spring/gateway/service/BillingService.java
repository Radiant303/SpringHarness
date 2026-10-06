package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.entity.ModelRate;
import com.spring.gateway.entity.PointsHold;
import com.spring.gateway.entity.PointsLedger;
import com.spring.gateway.entity.SystemSetting;
import com.spring.gateway.entity.UsageRecord;
import com.spring.gateway.mapper.ModelRateMapper;
import com.spring.gateway.mapper.PointsHoldMapper;
import com.spring.gateway.mapper.PointsLedgerMapper;
import com.spring.gateway.mapper.UsageRecordMapper;
import com.spring.gateway.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

/**
 * 积分计费：预扣-结算交易系统。
 *
 * <p>资金流：turn 派发时 {@link #preDeduct} 按兜底资费卡 × 预估档位建预扣（同步拦余额不足）；
 * turn 结束的 lifecycle 事件驱动 {@link #recordUsageAndSettle} 按实际模型资费多退少补；
 * 未真正运行的轮次与过期在途预扣经 {@link #releaseHold} 全额退回。
 *
 * <p>不变量：余额只经 {@link #applyDelta} 变动（行锁串行），每次变动必配一条流水；
 * 预扣收口（结算/释放）靠条件状态迁移保证全局只有一个赢家。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BillingService {

    /** 费率的单位分母：每百万 tokens。 */
    private static final BigDecimal MILLION = new BigDecimal("1000000");

    /** 金额计算精度（与 DECIMAL(20,6) 列一致）。 */
    private static final int SCALE = 6;

    private final UserMapper userMapper;
    private final ModelRateMapper modelRateMapper;
    private final PointsHoldMapper pointsHoldMapper;
    private final PointsLedgerMapper pointsLedgerMapper;
    private final UsageRecordMapper usageRecordMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final SystemSettingService systemSettingService;

    /**
     * 派发预扣：按兜底资费卡 × 预估档位估算，余额不足抛 409，整单零副作用。
     *
     * @param userId 用户 ID
     * @param turnId 轮次 ID（预扣单号）
     * @throws BizException 余额不足（409）；用户不存在（404）
     */
    @Transactional
    public void preDeduct(long userId, String turnId) {
        if (pointsHoldMapper.selectById(turnId) != null) {
            return;  // 幂等：同一 turnId 重复派发不重复扣
        }
        BigDecimal amount = estimateAmount();
        // 先扣款再建单：余额不足在这里直接抛出，hold/流水零副作用
        BigDecimal after = applyDelta(userId, amount.negate(), false);
        PointsHold hold = new PointsHold();
        hold.setTurnId(turnId);
        hold.setUserId(userId);
        hold.setAmount(amount);
        hold.setStatus(PointsHold.STATUS_HELD);
        hold.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        pointsHoldMapper.insert(hold);
        insertLedger(userId, amount.negate(), after, PointsLedger.TYPE_HOLD, turnId, null, null, null);
        log.info("积分预扣: turnId={} userId={} amount={} 余额={}", turnId, userId, amount, after);
    }

    /**
     * usage 落账与结算：同一事务，重放时撞 usage_records.turn_id 唯一键整单跳过。
     *
     * @param record 装配好的用量记录（turnId/userId/modelName/token 量已填）
     */
    @Transactional
    public void recordUsageAndSettle(UsageRecord record) {
        try {
            usageRecordMapper.insert(record);
        } catch (DuplicateKeyException e) {
            log.info("turn 用量已存在，用量与结算整单跳过: turnId={}", record.getTurnId());
            return;
        }
        settle(record);
    }

    /**
     * 释放预扣并全额退回；无在途预扣时静默跳过。turnId 为 null（透传轮等）直接返回。
     *
     * @param turnId 轮次 ID
     */
    @Transactional
    public void releaseHold(String turnId) {
        if (turnId == null) {
            return;
        }
        if (pointsHoldMapper.transition(turnId, PointsHold.STATUS_RELEASED) != 1) {
            return;  // 不存在或已收口
        }
        PointsHold hold = pointsHoldMapper.selectById(turnId);
        BigDecimal after = applyDelta(hold.getUserId(), hold.getAmount(), true);
        insertLedger(hold.getUserId(), hold.getAmount(), after, PointsLedger.TYPE_RELEASE,
                turnId, null, null, null);
        log.info("预扣释放退回: turnId={} userId={} amount={} 余额={}",
                turnId, hold.getUserId(), hold.getAmount(), after);
    }

    /**
     * 站长调账（充值/扣减）：写 ADJUST 流水，余额不许调成负。
     *
     * @param operatorId 操作人（站长）用户 ID
     * @param targetId   目标用户 ID
     * @param delta      变动额（正=充值，负=扣减，不能为 0）
     * @param reason     事由
     * @throws BizException 金额非法（400）；余额不足（409）
     */
    @Transactional
    public void adjust(long operatorId, long targetId, BigDecimal delta, String reason) {
        if (delta == null || delta.signum() == 0) {
            throw new BizException(400, "调账金额不能为 0");
        }
        BigDecimal after = applyDelta(targetId, delta, false);
        insertLedger(targetId, delta, after, PointsLedger.TYPE_ADJUST,
                String.valueOf(idGenerator.nextId()), null, operatorId, reason);
        log.info("积分调账: operator={} target={} delta={} 余额={} 事由={}",
                operatorId, targetId, delta, after, reason);
    }

    /**
     * 当前余额（非加锁读，展示用）
     *
     * @param userId 用户 ID
     * @return 积分余额
     * @throws BizException 用户不存在（404）
     */
    public BigDecimal balanceOf(long userId) {
        com.spring.gateway.entity.User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(404, "用户不存在");
        }
        return user.getPointsBalance() == null ? BigDecimal.ZERO : user.getPointsBalance();
    }

    /**
     * 兑换码积分入账：写 REDEEM 流水（ref_id = 码 ID，(type, ref_id) 唯一作幂等锚）。
     * 必须在调用方的事务内使用（与配额增量同一事务，同生共死）。
     *
     * @param userId 兑换人用户 ID
     * @param points 入账积分（必须为正；零面值码由调用方跳过本方法）
     * @param refId  码 ID（字符串）
     * @return 入账后余额
     */
    public BigDecimal grantRedeem(long userId, BigDecimal points, String refId) {
        BigDecimal after = applyDelta(userId, points, false);
        insertLedger(userId, points, after, PointsLedger.TYPE_REDEEM, refId, null, null, null);
        log.info("兑换码入账: userId={} refId={} points={} 余额={}", userId, refId, points, after);
        return after;
    }

    /**
     * 用户的最近流水（按 id 倒序）
     *
     * @param userId 用户 ID
     * @param limit  条数上限
     * @return 流水列表
     */
    public List<PointsLedger> recentLedger(long userId, int limit) {
        return pointsLedgerMapper.selectList(new LambdaQueryWrapper<PointsLedger>()
                .eq(PointsLedger::getUserId, userId)
                .orderByDesc(PointsLedger::getId)
                .last("LIMIT " + limit));
    }

    /** 结算：有在途预扣按净差多退少补；无预扣（wake 轮等）按实际成本直接扣。 */
    private void settle(UsageRecord record) {
        BigDecimal cost = computeCost(record);
        String turnId = record.getTurnId();
        if (turnId != null && pointsHoldMapper.transition(turnId, PointsHold.STATUS_SETTLED) == 1) {
            PointsHold hold = pointsHoldMapper.selectById(turnId);
            BigDecimal delta = cost.subtract(hold.getAmount());  // 正=少补，负=多退
            if (delta.signum() != 0) {
                BigDecimal change = delta.negate();
                BigDecimal after = applyDelta(hold.getUserId(), change, true);
                insertLedger(hold.getUserId(), change, after, PointsLedger.TYPE_SETTLE,
                        turnId, record.getModelName(), null, null);
                log.info("预扣结算: turnId={} userId={} 预扣={} 实际={} 净差={} 余额={}",
                        turnId, hold.getUserId(), hold.getAmount(), cost, delta, after);
            } else {
                log.info("预扣结算（实扣=预扣，无净差）: turnId={} amount={}", turnId, cost);
            }
        } else if (cost.signum() > 0) {
            BigDecimal after = applyDelta(record.getUserId(), cost.negate(), true);
            insertLedger(record.getUserId(), cost.negate(), after, PointsLedger.TYPE_DIRECT,
                    turnId, record.getModelName(), null, null);
            log.info("无预扣直接结算: turnId={} userId={} model={} 成本={} 余额={}",
                    turnId, record.getUserId(), record.getModelName(), cost, after);
        }
    }

    /** 实际成本：按 usage 的 modelName 精确匹配启用中的资费卡，否则回落兜底卡。 */
    private BigDecimal computeCost(UsageRecord record) {
        ModelRate rate = findRate(record.getModelName());
        if (rate == null) {
            return BigDecimal.ZERO;
        }
        long cacheRead = record.getCacheReadTokens() == null ? 0L : record.getCacheReadTokens();
        long cacheWrite = record.getCacheWriteTokens() == null ? 0L : record.getCacheWriteTokens();
        long input = record.getInputTokens() == null ? 0L : record.getInputTokens();
        long output = record.getOutputTokens() == null ? 0L : record.getOutputTokens();
        // input_tokens 是 inclusive 桶：无缓存输入 = 总输入 - 缓存命中 - 缓存写入
        long uncached = Math.max(0L, input - cacheRead - cacheWrite);
        return costOf(rate, uncached, cacheRead, cacheWrite, output);
    }

    /** 预扣估算：兜底卡 × 系统设置的预估档位（缓存写入不预估，结算按实际计）。 */
    private BigDecimal estimateAmount() {
        ModelRate rate = findRate(null);
        if (rate == null) {
            return BigDecimal.ZERO;
        }
        long estCacheRead = systemSettingService.getLong(
                SystemSetting.KEY_BILLING_EST_CACHE_READ_TOKENS, 90000L);
        long estInput = systemSettingService.getLong(
                SystemSetting.KEY_BILLING_EST_INPUT_TOKENS, 10000L);
        long estOutput = systemSettingService.getLong(
                SystemSetting.KEY_BILLING_EST_OUTPUT_TOKENS, 20000L);
        return costOf(rate, estInput, estCacheRead, 0L, estOutput);
    }

    /** 资费卡查找：精确匹配且启用 → 用之；否则兜底卡（停用/缺失 → null = 免费）。 */
    private ModelRate findRate(String modelName) {
        if (modelName != null && !ModelRate.DEFAULT_MODEL_NAME.equals(modelName)) {
            ModelRate row = modelRateMapper.selectOne(new LambdaQueryWrapper<ModelRate>()
                    .eq(ModelRate::getModelName, modelName));
            if (row != null && Boolean.TRUE.equals(row.getEnabled())) {
                return row;
            }
        }
        ModelRate fallback = modelRateMapper.selectOne(new LambdaQueryWrapper<ModelRate>()
                .eq(ModelRate::getModelName, ModelRate.DEFAULT_MODEL_NAME));
        return fallback != null && Boolean.TRUE.equals(fallback.getEnabled()) ? fallback : null;
    }

    /** 成本 = Σ(费率 × tokens) / 1e6，六位小数。 */
    private static BigDecimal costOf(ModelRate rate, long uncached, long cacheRead,
                                     long cacheWrite, long output) {
        BigDecimal total = rate.getInputPoints().multiply(BigDecimal.valueOf(uncached))
                .add(rate.getCacheReadPoints().multiply(BigDecimal.valueOf(cacheRead)))
                .add(rate.getCacheWritePoints().multiply(BigDecimal.valueOf(cacheWrite)))
                .add(rate.getOutputPoints().multiply(BigDecimal.valueOf(output)));
        return total.divide(MILLION, SCALE, RoundingMode.HALF_UP);
    }

    /**
     * 余额变动唯一收口：行锁读 → 算 → 负余额且不允许时抛 409 → 写回。
     *
     * @throws BizException 用户不存在（404）；余额不足（409）
     */
    private BigDecimal applyDelta(long userId, BigDecimal delta, boolean allowNegative) {
        BigDecimal balance = userMapper.selectBalanceForUpdate(userId);
        if (balance == null) {
            throw new BizException(404, "用户不存在");
        }
        BigDecimal after = balance.add(delta);
        if (!allowNegative && after.signum() < 0) {
            throw new BizException(409, "积分不足：当前 "
                    + balance.stripTrailingZeros().toPlainString() + "，本次需 "
                    + delta.negate().stripTrailingZeros().toPlainString());
        }
        userMapper.updateBalance(userId, after);
        return after;
    }

    private void insertLedger(long userId, BigDecimal change, BigDecimal after, String type,
                              String refId, String modelName, Long operatorId, String reason) {
        PointsLedger row = new PointsLedger();
        row.setId(idGenerator.nextId());
        row.setUserId(userId);
        row.setChangeAmount(change);
        row.setBalanceAfter(after);
        row.setType(type);
        row.setRefId(refId);
        row.setModelName(modelName);
        row.setOperatorId(operatorId);
        row.setReason(reason);
        row.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        pointsLedgerMapper.insert(row);
    }
}
