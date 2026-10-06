package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.MyRedemptionView;
import com.spring.gateway.dto.PointsLedgerView;
import com.spring.gateway.dto.RedeemRequest;
import com.spring.gateway.dto.RedeemResultView;
import com.spring.gateway.service.BillingService;
import com.spring.gateway.service.RedeemService;
import com.spring.gateway.service.WorkService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 用户侧积分自查、存储概览与兑换码兑换。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@RestController
@RequestMapping("/api/billing")
@RequiredArgsConstructor
public class BillingController {

    /** 自查流水的条数。 */
    private static final int RECENT_LIMIT = 10;

    private final BillingService billingService;
    private final RedeemService redeemService;
    private final WorkService workService;

    /**
     * 当前用户的积分余额、最近 10 条流水与存储概览
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @return 余额 + 流水列表 + 存储概览
     */
    @GetMapping("/me")
    public Result<Map<String, Object>> me(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        BigDecimal balance = billingService.balanceOf(userId);
        List<PointsLedgerView> ledger = billingService.recentLedger(userId, RECENT_LIMIT)
                .stream().map(AdminPointsController::toLedgerView).toList();
        WorkService.StorageOverview quota = workService.storageOverview(userId);
        Map<String, Object> data = new HashMap<>();
        data.put("balance", balance);
        data.put("ledger", ledger);
        data.put("quota_bytes", quota.quotaBytes());
        data.put("storage_used_bytes", quota.usedBytes());
        data.put("work_quota_bytes", quota.workMaxBytes());
        return Result.ok(data);
    }

    /**
     * 当前用户的兑换记录（含纯配额兑换；最近 10 条）
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @return 兑换记录列表
     */
    @GetMapping("/redemptions")
    public Result<List<MyRedemptionView>> redemptions(
            @RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        return Result.ok(redeemService.myRedemptions(userId, RECENT_LIMIT).stream()
                .map(row -> new MyRedemptionView(
                        row.getCode(),
                        row.getPointsAmount(),
                        row.getStorageDeltaBytes(),
                        row.getWorkQuotaDeltaBytes(),
                        TimeFormat.isoUtc(row.getRedeemedAt())))
                .toList());
    }

    /**
     * 兑换码兑换（任何登录用户；一次性，并发安全）
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @param req    兑换码（允许连字符/空格/小写）
     * @return 实发三项面值 + 入账后余额
     */
    @PostMapping("/redeem")
    public Result<RedeemResultView> redeem(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                                           @Valid @RequestBody RedeemRequest req) {
        return Result.ok(redeemService.redeem(userId, req.code()));
    }
}
