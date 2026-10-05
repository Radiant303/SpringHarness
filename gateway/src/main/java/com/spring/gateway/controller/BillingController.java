package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.Result;
import com.spring.gateway.dto.PointsLedgerView;
import com.spring.gateway.service.BillingService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * 用户侧积分自查：余额与最近流水。
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

    /**
     * 当前用户的积分余额与最近 10 条流水
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @return 余额 + 流水列表
     */
    @GetMapping("/me")
    public Result<Map<String, Object>> me(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        BigDecimal balance = billingService.balanceOf(userId);
        List<PointsLedgerView> ledger = billingService.recentLedger(userId, RECENT_LIMIT)
                .stream().map(AdminPointsController::toLedgerView).toList();
        return Result.ok(Map.of("balance", balance, "ledger", ledger));
    }
}
