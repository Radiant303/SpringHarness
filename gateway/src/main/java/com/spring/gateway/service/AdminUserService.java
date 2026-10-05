package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.entity.User;
import com.spring.gateway.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 用户管理业务（管理后台）。
 *
 * <p>操作边界：站长（owner）可操作任何人但站长账号本身不可被禁用/变更角色；
 * 管理员（admin）只能操作普通用户（user）账号。owner 角色不可经 API 授予，
 * 唯一的站长来自首用户引导（或手动 SQL）。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Service
@RequiredArgsConstructor
public class AdminUserService {

    private final UserMapper userMapper;
    private final BCryptPasswordEncoder passwordEncoder;

    /**
     * 全部用户，按注册时间升序
     *
     * @return 用户列表
     */
    public List<User> list() {
        return userMapper.selectList(new LambdaQueryWrapper<User>()
                .orderByAsc(User::getCreatedAt)
                .orderByAsc(User::getId));
    }

    /**
     * 禁用/启用账号；站长账号不可被禁用
     *
     * @param actorRole 操作者角色
     * @param targetId  目标用户 ID
     * @param status    目标状态（active/disabled）
     * @throws BizException 目标不存在（404）；越权（403）
     */
    public void setStatus(String actorRole, Long targetId, String status) {
        User target = requireTarget(targetId);
        requireOperable(actorRole, target);
        if (User.ROLE_OWNER.equals(target.getRole()) && User.STATUS_DISABLED.equals(status)) {
            throw new BizException(403, "站长账号不可被禁用");
        }
        User row = new User();
        row.setId(targetId);
        row.setStatus(status);
        userMapper.updateById(row);
    }

    /**
     * 任命/罢免管理员；仅站长可调用，此处再校验一次角色
     *
     * @param actorRole 操作者角色
     * @param targetId  目标用户 ID
     * @param role      目标角色（admin/user）
     * @throws BizException 目标不存在（404）；非站长操作或目标为站长（403）
     */
    public void setRole(String actorRole, Long targetId, String role) {
        if (!User.ROLE_OWNER.equals(actorRole)) {
            throw new BizException(403, "仅站长可任命管理员");
        }
        User target = requireTarget(targetId);
        if (User.ROLE_OWNER.equals(target.getRole())) {
            throw new BizException(403, "站长角色不可变更");
        }
        User row = new User();
        row.setId(targetId);
        row.setRole(role);
        userMapper.updateById(row);
    }

    /**
     * 重置用户密码（BCrypt 重新哈希）
     *
     * @param actorRole 操作者角色
     * @param targetId  目标用户 ID
     * @param password  新密码明文
     * @throws BizException 目标不存在（404）；越权（403）
     */
    public void resetPassword(String actorRole, Long targetId, String password) {
        requireOperable(actorRole, requireTarget(targetId));
        User row = new User();
        row.setId(targetId);
        row.setPasswordHash(passwordEncoder.encode(password));
        userMapper.updateById(row);
    }

    /**
     * 调整存储配额（字节）
     *
     * @param actorRole  操作者角色
     * @param targetId   目标用户 ID
     * @param quotaBytes 新配额
     * @throws BizException 目标不存在（404）；越权（403）
     */
    public void setQuota(String actorRole, Long targetId, Long quotaBytes) {
        requireOperable(actorRole, requireTarget(targetId));
        User row = new User();
        row.setId(targetId);
        row.setQuotaBytes(quotaBytes);
        userMapper.updateById(row);
    }

    /**
     * 调整单工作区上限覆盖值（字节）；null 表示恢复跟随全局设置
     *
     * @param actorRole  操作者角色
     * @param targetId   目标用户 ID
     * @param quotaBytes 覆盖值或 null
     * @throws BizException 目标不存在（404）；越权（403）
     */
    public void setWorkQuota(String actorRole, Long targetId, Long quotaBytes) {
        requireOperable(actorRole, requireTarget(targetId));
        // updateById 默认忽略 null 字段，写 NULL（恢复跟随全局）必须显式 set
        userMapper.update(null, new LambdaUpdateWrapper<User>()
                .eq(User::getId, targetId)
                .set(User::getWorkQuotaBytes, quotaBytes));
    }

    private User requireTarget(Long targetId) {
        User target = userMapper.selectById(targetId);
        if (target == null) {
            throw new BizException(404, "用户不存在");
        }
        return target;
    }

    /** 管理员只能操作普通用户账号；站长不受限（另有针对目标为站长的专门限制）。 */
    private void requireOperable(String actorRole, User target) {
        if (User.ROLE_ADMIN.equals(actorRole) && !User.ROLE_USER.equals(target.getRole())) {
            throw new BizException(403, "管理员只能操作用户账号");
        }
    }
}
