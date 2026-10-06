package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.AdminRedeemCodeView;
import com.spring.gateway.dto.AdminRedeemCreateRequest;
import com.spring.gateway.entity.RedeemCode;
import com.spring.gateway.entity.User;
import com.spring.gateway.service.RedeemService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;

/**
 * 兑换码管理接口：生成/作废仅站长，列表查看对 owner/admin 开放。
 *
 * @author hanbing
 * @since 2026-10-06
 */
@RestController
@RequestMapping("/api/admin/redeem-codes")
@RequiredArgsConstructor
public class AdminRedeemController {

    /** 合法的状态过滤值。 */
    private static final Set<String> STATUSES = Set.of(
            RedeemCode.STATUS_ACTIVE, RedeemCode.STATUS_REDEEMED, RedeemCode.STATUS_REVOKED);

    private final RedeemService redeemService;

    /**
     * 批量生成兑换码（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param actorId   当前用户 ID（拦截器注入）
     * @param req       数量、三项面值、有效小时数
     * @return 生成的码列表
     */
    @PostMapping
    public Result<List<AdminRedeemCodeView>> generate(
            @RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
            @RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long actorId,
            @Valid @RequestBody AdminRedeemCreateRequest req) {
        requireOwner(actorRole);
        return Result.ok(redeemService.generate(actorId, req).stream()
                .map(AdminRedeemController::toView).toList());
    }

    /**
     * 兑换码列表（owner/admin；可按状态过滤）
     *
     * @param status 状态过滤（缺省全部）
     * @return 码列表（按 id 倒序）
     */
    @GetMapping
    public Result<List<AdminRedeemCodeView>> list(
            @RequestParam(required = false) String status) {
        if (status != null && !STATUSES.contains(status)) {
            throw new BizException(400, "非法的状态过滤值");
        }
        return Result.ok(redeemService.list(status).stream()
                .map(AdminRedeemController::toView).toList());
    }

    /**
     * 作废未使用的兑换码（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        码 ID
     * @return 空数据返回体
     */
    @PostMapping("/{id}/revoke")
    public Result<Void> revoke(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                               @PathVariable Long id) {
        requireOwner(actorRole);
        redeemService.revoke(id);
        return Result.ok(null);
    }

    private static void requireOwner(String actorRole) {
        if (!User.ROLE_OWNER.equals(actorRole)) {
            throw new BizException(403, "仅站长可管理兑换码");
        }
    }

    private static AdminRedeemCodeView toView(RedeemCode row) {
        boolean expired = RedeemCode.STATUS_ACTIVE.equals(row.getStatus())
                && row.getExpiresAt() != null
                && !row.getExpiresAt().isAfter(LocalDateTime.now(ZoneOffset.UTC));
        return new AdminRedeemCodeView(
                String.valueOf(row.getId()),
                row.getCode(),
                row.getStatus(),
                expired,
                row.getPointsAmount(),
                row.getStorageDeltaBytes(),
                row.getWorkQuotaDeltaBytes(),
                row.getExpiresAt() == null ? null : TimeFormat.isoUtc(row.getExpiresAt()),
                String.valueOf(row.getCreatedBy()),
                row.getRedeemedBy() == null ? null : String.valueOf(row.getRedeemedBy()),
                row.getRedeemedAt() == null ? null : TimeFormat.isoUtc(row.getRedeemedAt()),
                TimeFormat.isoUtc(row.getCreatedAt()));
    }
}
