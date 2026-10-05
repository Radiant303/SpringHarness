package com.spring.gateway.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.PointsHoldView;
import com.spring.gateway.dto.PointsLedgerView;
import com.spring.gateway.entity.PointsHold;
import com.spring.gateway.entity.PointsLedger;
import com.spring.gateway.mapper.PointsHoldMapper;
import com.spring.gateway.mapper.PointsLedgerMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 积分对账视图：流水与在途预扣查询（owner/admin）。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@RestController
@RequestMapping("/api/admin/points")
@RequiredArgsConstructor
public class AdminPointsController {

    /** 流水查询的条数上限。 */
    private static final int LEDGER_LIMIT_MAX = 500;

    private final PointsLedgerMapper pointsLedgerMapper;
    private final PointsHoldMapper pointsHoldMapper;

    /**
     * 积分流水（按 id 倒序，可按用户过滤）
     *
     * @param userId 只看该用户；缺省为全部
     * @param limit  条数（默认 100，上限 500）
     * @return 流水列表
     */
    @GetMapping("/ledger")
    public Result<List<PointsLedgerView>> ledger(@RequestParam(required = false) Long userId,
                                                 @RequestParam(required = false) Integer limit) {
        int capped = limit == null ? 100 : Math.max(1, Math.min(limit, LEDGER_LIMIT_MAX));
        List<PointsLedger> rows = pointsLedgerMapper.selectList(new LambdaQueryWrapper<PointsLedger>()
                .eq(userId != null, PointsLedger::getUserId, userId)
                .orderByDesc(PointsLedger::getId)
                .last("LIMIT " + capped));
        return Result.ok(rows.stream().map(AdminPointsController::toLedgerView).toList());
    }

    /**
     * 预扣单查询（默认只看在途 HELD）
     *
     * @param status 状态过滤（HELD/SETTLED/RELEASED），缺省 HELD
     * @return 预扣列表
     */
    @GetMapping("/holds")
    public Result<List<PointsHoldView>> holds(@RequestParam(defaultValue = "HELD") String status) {
        List<PointsHold> rows = pointsHoldMapper.selectList(new LambdaQueryWrapper<PointsHold>()
                .eq(PointsHold::getStatus, status)
                .orderByDesc(PointsHold::getCreatedAt)
                .last("LIMIT " + LEDGER_LIMIT_MAX));
        return Result.ok(rows.stream().map(AdminPointsController::toHoldView).toList());
    }

    static PointsLedgerView toLedgerView(PointsLedger row) {
        return new PointsLedgerView(
                String.valueOf(row.getId()),
                String.valueOf(row.getUserId()),
                row.getChangeAmount(),
                row.getBalanceAfter(),
                row.getType(),
                row.getRefId(),
                row.getModelName(),
                row.getOperatorId() == null ? null : String.valueOf(row.getOperatorId()),
                row.getReason(),
                TimeFormat.isoUtc(row.getCreatedAt()));
    }

    static PointsHoldView toHoldView(PointsHold row) {
        return new PointsHoldView(
                row.getTurnId(),
                String.valueOf(row.getUserId()),
                row.getAmount(),
                row.getStatus(),
                TimeFormat.isoUtc(row.getCreatedAt()),
                row.getSettledAt() == null ? null : TimeFormat.isoUtc(row.getSettledAt()));
    }
}
