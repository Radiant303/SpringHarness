package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.AdminPasswordRequest;
import com.spring.gateway.dto.AdminQuotaRequest;
import com.spring.gateway.dto.AdminRoleRequest;
import com.spring.gateway.dto.AdminStatusRequest;
import com.spring.gateway.dto.AdminUserView;
import com.spring.gateway.dto.AdminWorkQuotaRequest;
import com.spring.gateway.service.AdminUserService;
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
 * 用户管理接口。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@RestController
@RequestMapping("/api/admin/users")
@RequiredArgsConstructor
public class AdminUserController {

    private final AdminUserService adminUserService;

    /**
     * 用户列表
     *
     * @return 全部用户（按注册时间升序）
     */
    @GetMapping
    public Result<List<AdminUserView>> list() {
        return Result.ok(adminUserService.list().stream().map(AdminUserController::toView).toList());
    }

    /**
     * 禁用/启用账号；站长不可被禁用，管理员只能操作用户账号
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        目标用户 ID
     * @param req       目标状态
     * @return 空数据返回体
     */
    @PostMapping("/{id}/status")
    public Result<Void> setStatus(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                  @PathVariable Long id,
                                  @Valid @RequestBody AdminStatusRequest req) {
        adminUserService.setStatus(actorRole, id, req.status());
        return Result.ok(null);
    }

    /**
     * 任命/罢免管理员（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        目标用户 ID
     * @param req       目标角色（admin/user）
     * @return 空数据返回体
     */
    @PostMapping("/{id}/role")
    public Result<Void> setRole(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                @PathVariable Long id,
                                @Valid @RequestBody AdminRoleRequest req) {
        adminUserService.setRole(actorRole, id, req.role());
        return Result.ok(null);
    }

    /**
     * 重置用户密码
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        目标用户 ID
     * @param req       新密码
     * @return 空数据返回体
     */
    @PostMapping("/{id}/password")
    public Result<Void> resetPassword(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                      @PathVariable Long id,
                                      @Valid @RequestBody AdminPasswordRequest req) {
        adminUserService.resetPassword(actorRole, id, req.password());
        return Result.ok(null);
    }

    /**
     * 调整存储配额
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        目标用户 ID
     * @param req       新配额（字节）
     * @return 空数据返回体
     */
    @PostMapping("/{id}/quota")
    public Result<Void> setQuota(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                 @PathVariable Long id,
                                 @Valid @RequestBody AdminQuotaRequest req) {
        adminUserService.setQuota(actorRole, id, req.quotaBytes());
        return Result.ok(null);
    }

    /**
     * 调整单工作区上限覆盖值；quotaBytes 为 null 时恢复跟随全局设置
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param id        目标用户 ID
     * @param req       覆盖值或 null
     * @return 空数据返回体
     */
    @PostMapping("/{id}/work-quota")
    public Result<Void> setWorkQuota(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                     @PathVariable Long id,
                                     @Valid @RequestBody AdminWorkQuotaRequest req) {
        adminUserService.setWorkQuota(actorRole, id, req.quotaBytes());
        return Result.ok(null);
    }

    private static AdminUserView toView(com.spring.gateway.entity.User user) {
        return new AdminUserView(
                String.valueOf(user.getId()),  // 字符串下发：雪花 ID 超 2^53，JS 数字会丢精度
                user.getUsername(),
                user.getRole(),
                user.getStatus(),
                user.getQuotaBytes(),
                user.getWorkQuotaBytes(),
                TimeFormat.isoUtc(user.getCreatedAt()));
    }
}
