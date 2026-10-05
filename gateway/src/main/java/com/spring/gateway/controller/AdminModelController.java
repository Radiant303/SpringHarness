package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.AdminModelRequest;
import com.spring.gateway.dto.AdminModelView;
import com.spring.gateway.entity.ModelRate;
import com.spring.gateway.entity.User;
import com.spring.gateway.service.AdminModelService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 模型资费卡管理接口：查看对 owner/admin 开放，增删改仅站长。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@RestController
@RequestMapping("/api/admin/models")
@RequiredArgsConstructor
public class AdminModelController {

    private final AdminModelService adminModelService;

    /**
     * 资费卡列表（default 行置顶）
     *
     * @return 全部资费卡
     */
    @GetMapping
    public Result<List<AdminModelView>> list() {
        return Result.ok(adminModelService.list().stream().map(AdminModelController::toView).toList());
    }

    /**
     * 新建资费卡（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param req       模型名与四项费率
     * @return 新建行
     */
    @PostMapping
    public Result<AdminModelView> create(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                         @Valid @RequestBody AdminModelRequest req) {
        requireOwner(actorRole);
        return Result.ok(toView(adminModelService.create(req)));
    }

    /**
     * 修改资费卡（仅站长）；兜底卡不可改名、不可停用
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        资费卡 ID
     * @param req       新值
     * @return 空数据返回体
     */
    @PostMapping("/{id}")
    public Result<Void> update(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                               @PathVariable Long id,
                               @Valid @RequestBody AdminModelRequest req) {
        requireOwner(actorRole);
        adminModelService.update(id, req);
        return Result.ok(null);
    }

    /**
     * 删除资费卡（仅站长）；兜底卡不可删除
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        资费卡 ID
     * @return 空数据返回体
     */
    @PostMapping("/{id}/delete")
    public Result<Void> delete(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                               @PathVariable Long id) {
        requireOwner(actorRole);
        adminModelService.delete(id);
        return Result.ok(null);
    }

    private static void requireOwner(String actorRole) {
        if (!User.ROLE_OWNER.equals(actorRole)) {
            throw new BizException(403, "仅站长可管理模型资费");
        }
    }

    private static AdminModelView toView(ModelRate row) {
        return new AdminModelView(
                String.valueOf(row.getId()),
                row.getModelName(),
                row.getInputPoints(),
                row.getCacheReadPoints(),
                row.getCacheWritePoints(),
                row.getOutputPoints(),
                row.getEnabled(),
                TimeFormat.isoUtc(row.getCreatedAt()),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }
}
