package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.RedeemFailRateLimiter;
import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.dto.AdminRedeemCreateRequest;
import com.spring.gateway.dto.RedeemResultView;
import com.spring.gateway.entity.RedeemCode;
import com.spring.gateway.mapper.RedeemCodeMapper;
import com.spring.gateway.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 兑换码：站长生成 → 用户兑换（积分 + 存储配额增量 + work 区上限增量）。
 *
 * <p>一次性靠条件 UPDATE 抢占保证（影响行数唯一赢家），发奖与抢占同事务，
 * 失败整体回滚；积分部分经 BillingService 写 REDEEM 流水，(type, ref_id)
 * 唯一约束兜底幂等。过期只在兑换时按 expires_at 判定，不建 EXPIRED 状态。
 *
 * @author hanbing
 * @since 2026-10-06
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RedeemService {

    /** 码字符表：Crockford Base32，去掉 I/L/O/U 歧义字符。 */
    private static final String ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

    /** 码长（规范形，不含连字符）。 */
    private static final int CODE_LENGTH = 16;

    /** 单个码撞唯一索引的最大重试次数。 */
    private static final int MAX_GENERATE_ATTEMPTS = 5;

    /** MB → 字节。 */
    private static final long MB = 1024L * 1024L;

    private final RedeemCodeMapper redeemCodeMapper;
    private final UserMapper userMapper;
    private final BillingService billingService;
    private final SystemSettingService systemSettingService;
    private final SnowflakeIdGenerator idGenerator;
    private final RedeemFailRateLimiter failRateLimiter;
    private final SecureRandom secureRandom = new SecureRandom();

    /**
     * 批量生成兑换码（站长）。
     *
     * @param actorId 生成人（站长）用户 ID
     * @param req     生成请求
     * @return 生成的码行
     * @throws BizException 三项面值全为 0（400）
     */
    @Transactional
    public List<RedeemCode> generate(long actorId, AdminRedeemCreateRequest req) {
        BigDecimal points = req.points() == null ? BigDecimal.ZERO : req.points();
        long storageBytes = (req.storageMb() == null ? 0L : req.storageMb()) * MB;
        long workQuotaBytes = (req.workQuotaMb() == null ? 0L : req.workQuotaMb()) * MB;
        if (points.signum() == 0 && storageBytes == 0 && workQuotaBytes == 0) {
            throw new BizException(400, "三项面值至少一项大于 0");
        }
        LocalDateTime expiresAt = req.expiresInHours() == null ? null
                : LocalDateTime.now(ZoneOffset.UTC).plusHours(req.expiresInHours());

        List<RedeemCode> created = new ArrayList<>(req.count());
        for (int i = 0; i < req.count(); i++) {
            created.add(insertOne(actorId, points, storageBytes, workQuotaBytes, expiresAt));
        }
        log.info("兑换码生成: actor={} count={} points={} storage={} workQuota={} expiresAt={}",
                actorId, req.count(), points, storageBytes, workQuotaBytes, expiresAt);
        return created;
    }

    /**
     * 用户兑换：限流探查 → 抢占 → 同事务发奖。
     *
     * <p>失败限流：进入时探查桶余量，失败由限流器计数、成功清零；
     * 桶空直接 429，连有效码也挡——暴力枚举场景下不再透传任何码状态信息。
     *
     * @param userId  当前用户 ID
     * @param rawCode 用户输入的兑换码
     * @return 实发三项面值 + 入账后余额
     * @throws BizException 失败次数超限（429）；码不存在（404）；已使用/已过期/已作废（409）
     */
    @Transactional
    public RedeemResultView redeem(long userId, String rawCode) {
        if (!failRateLimiter.tryEnter(userId)) {
            throw new BizException(429, "兑换失败次数过多，请 1 分钟后再试");
        }
        try {
            String code = normalize(rawCode);
            if (redeemCodeMapper.claim(code, userId) != 1) {
                throw claimFailure(code);
            }
            RedeemCode row = selectByCode(code);

            BigDecimal balanceAfter;
            if (row.getPointsAmount().signum() > 0) {
                balanceAfter = billingService.grantRedeem(userId, row.getPointsAmount(), String.valueOf(row.getId()));
            } else {
                balanceAfter = billingService.balanceOf(userId);
            }
            if (row.getStorageDeltaBytes() > 0) {
                userMapper.addQuotaBytes(userId, row.getStorageDeltaBytes());
            }
            if (row.getWorkQuotaDeltaBytes() > 0) {
                // NULL（跟随全局）时以兑换时的全局上限为基线落显式覆盖值
                userMapper.addWorkQuotaBytes(userId, systemSettingService.getWorkMaxBytes(),
                        row.getWorkQuotaDeltaBytes());
            }
            failRateLimiter.reset(userId);
            log.info("兑换成功: userId={} codeId={} points={} storage={} workQuota={} 余额={}",
                    userId, row.getId(), row.getPointsAmount(), row.getStorageDeltaBytes(),
                    row.getWorkQuotaDeltaBytes(), balanceAfter);
            return new RedeemResultView(row.getPointsAmount(), row.getStorageDeltaBytes(),
                    row.getWorkQuotaDeltaBytes(), balanceAfter);
        } catch (BizException e) {
            failRateLimiter.recordFailure(userId);
            throw e;
        }
    }

    /**
     * 作废未使用的码（站长）。
     *
     * @param id 码 ID
     * @throws BizException 码不存在（404）；非 ACTIVE（409）
     */
    @Transactional
    public void revoke(long id) {
        if (redeemCodeMapper.revoke(id) == 1) {
            log.info("兑换码作废: id={}", id);
            return;
        }
        RedeemCode row = redeemCodeMapper.selectById(id);
        if (row == null) {
            throw new BizException(404, "兑换码不存在");
        }
        throw new BizException(409, "仅待使用的兑换码可作废");
    }

    /**
     * 管理侧列表。
     *
     * @param statusFilter 状态过滤（null = 全部；须为 ACTIVE/REDEEMED/REVOKED）
     * @return 码行列表
     */
    public List<RedeemCode> list(String statusFilter) {
        LambdaQueryWrapper<RedeemCode> q = new LambdaQueryWrapper<RedeemCode>()
                .orderByDesc(RedeemCode::getId);
        if (statusFilter != null && !statusFilter.isBlank()) {
            q.eq(RedeemCode::getStatus, statusFilter);
        }
        return redeemCodeMapper.selectList(q);
    }

    /**
     * 用户自己的兑换记录。
     *
     * @param userId 用户 ID
     * @param limit  条数上限
     * @return 已兑换的码行
     */
    public List<RedeemCode> myRedemptions(long userId, int limit) {
        return redeemCodeMapper.selectList(new LambdaQueryWrapper<RedeemCode>()
                .eq(RedeemCode::getRedeemedBy, userId)
                .orderByDesc(RedeemCode::getRedeemedAt)
                .last("LIMIT " + limit));
    }

    /** 输入规范化。 */
    public static String normalize(String raw) {
        return raw == null ? "" : raw.replaceAll("[-\\s]", "").toUpperCase(Locale.ROOT);
    }

    /** 抢占失败后的精确报错：查行区分 不存在/已使用/已过期/已作废。 */
    private BizException claimFailure(String code) {
        RedeemCode row = selectByCode(code);
        if (row == null) {
            return new BizException(404, "兑换码不存在");
        }
        if (RedeemCode.STATUS_REDEEMED.equals(row.getStatus())) {
            return new BizException(409, "兑换码已被使用");
        }
        if (RedeemCode.STATUS_REVOKED.equals(row.getStatus())) {
            return new BizException(409, "兑换码已作废");
        }
        return new BizException(409, "兑换码已过期");
    }

    private RedeemCode selectByCode(String code) {
        return redeemCodeMapper.selectOne(new LambdaQueryWrapper<RedeemCode>()
                .eq(RedeemCode::getCode, code));
    }

    /** 插一行；撞 code 唯一索引换码重试。 */
    private RedeemCode insertOne(long actorId, BigDecimal points, long storageBytes,
                                 long workQuotaBytes, LocalDateTime expiresAt) {
        for (int attempt = 0; attempt < MAX_GENERATE_ATTEMPTS; attempt++) {
            RedeemCode row = new RedeemCode();
            row.setId(idGenerator.nextId());
            row.setCode(randomCode());
            row.setStatus(RedeemCode.STATUS_ACTIVE);
            row.setPointsAmount(points);
            row.setStorageDeltaBytes(storageBytes);
            row.setWorkQuotaDeltaBytes(workQuotaBytes);
            row.setExpiresAt(expiresAt);
            row.setCreatedBy(actorId);
            try {
                redeemCodeMapper.insert(row);
                return row;
            } catch (DuplicateKeyException e) {
                log.warn("兑换码撞唯一索引，换码重试（第 {} 次）", attempt + 1);
            }
        }
        throw new BizException(500, "兑换码生成失败，请重试");
    }

    private String randomCode() {
        StringBuilder sb = new StringBuilder(CODE_LENGTH);
        for (int i = 0; i < CODE_LENGTH; i++) {
            sb.append(ALPHABET.charAt(secureRandom.nextInt(ALPHABET.length())));
        }
        return sb.toString();
    }
}
