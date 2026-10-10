package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.JwtUtils;
import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.dto.ChangePasswordRequest;
import com.spring.gateway.dto.LoginRequest;
import com.spring.gateway.dto.RegisterRequest;
import com.spring.gateway.dto.ResetPasswordRequest;
import com.spring.gateway.dto.TokenResponse;
import com.spring.gateway.dto.UserResponse;
import com.spring.gateway.entity.User;
import com.spring.gateway.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

/**
 * 认证业务：用户注册与登录。
 *
 * <p>首个注册用户自动成为站长（owner），此后注册受 registration_open 系统设置约束。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserMapper userMapper;
    private final SnowflakeIdGenerator idGenerator;
    private final JwtUtils jwtUtils;
    private final BCryptPasswordEncoder passwordEncoder;
    private final SystemSettingService systemSettingService;
    private final MailCodeService mailCodeService;

    /**
     * 注册新用户；系统无用户时首个注册者成为站长（不受注册开关限制）。
     * 站长开启 mail.register_enabled 时，必须携带邮箱验证码：
     * 先查用户名/邮箱冲突，再验验证码（一次性，通过即销毁），最后落库。
     *
     * @param req 注册请求
     * @return 用户信息
     * @throws BizException 用户名或邮箱已存在（409）；验证码/邮箱不合法（400）；注册已关闭（403）
     */
    @Transactional
    public UserResponse register(RegisterRequest req) {
        boolean mailRequired = systemSettingService.isMailRegisterEnabled();
        String email = MailCodeService.normalize(req.email());
        String code = req.code() == null ? "" : req.code().trim();
        if (mailRequired) {
            if (email.isEmpty()) {
                throw new BizException(400, "邮箱不能为空");
            }
            if (!MailCodeService.isValidEmail(email)) {
                throw new BizException(400, "邮箱格式不正确");
            }
            if (!code.matches("\\d{6}")) {
                throw new BizException(400, "验证码为 6 位数字");
            }
        }
        boolean exists = userMapper.exists(
                new LambdaQueryWrapper<User>().eq(User::getUsername, req.username()));
        if (exists) {
            throw new BizException(409, "用户名已存在");
        }
        if (mailRequired) {
            boolean emailExists = userMapper.exists(
                    new LambdaQueryWrapper<User>().eq(User::getEmail, email));
            if (emailExists) {
                throw new BizException(409, "该邮箱已被注册");
            }
        }
        // 首用户引导：count==0 → owner；并发双注册理论可产生两个 owner，风险可忽略
        boolean bootstrap = userMapper.selectCount(null) == 0;
        if (!bootstrap && !systemSettingService.isRegistrationOpen()) {
            throw new BizException(403, "当前未开放注册");
        }
        if (mailRequired) {
            mailCodeService.verifyCode(email, code, MailCodeService.Scene.REGISTER);
        }
        User user = new User();
        user.setId(idGenerator.nextId());
        user.setUsername(req.username());
        // 邮箱只在验证码注册开启时记录（关闭时携带的邮箱未经核验，不入库）
        user.setEmail(mailRequired ? email : null);
        user.setPasswordHash(passwordEncoder.encode(req.password()));
        user.setRole(bootstrap ? User.ROLE_OWNER : User.ROLE_USER);
        user.setStatus(User.STATUS_ACTIVE);
        // 初始积分：站长 1000，其余 0（后续增减只经流水，无直接 set 入口）
        user.setPointsBalance(bootstrap ? new BigDecimal("1000") : BigDecimal.ZERO);
        try {
            userMapper.insert(user);
        } catch (DuplicateKeyException e) {
            // 先查后插存在并发窗口，由 username/email 唯一索引兜底；并发冲突时同样按已存在处理
            throw new BizException(409, "用户名或邮箱已存在");
        }
        return new UserResponse(String.valueOf(user.getId()), user.getUsername());
    }

    /**
     * 登录并签发 JWT。标识符可以是用户名，也可以是注册邮箱
     * （用户名查询未命中且输入形如邮箱时按邮箱再查一次；两种情况返回相同的 401，避免枚举）。
     *
     * @param req 登录请求
     * @return token 与用户信息
     * @throws BizException 用户不存在或密码错误（401）；账号被禁用（403）
     */
    public TokenResponse login(LoginRequest req) {
        User user = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getUsername, req.username()));
        if (user == null && req.username().contains("@")) {
            user = userMapper.selectOne(
                    new LambdaQueryWrapper<User>().eq(User::getEmail, MailCodeService.normalize(req.username())));
        }
        if (user == null || !passwordEncoder.matches(req.password(), user.getPasswordHash())) {
            throw new BizException(401, "用户名或密码错误");
        }
        if (User.STATUS_DISABLED.equals(user.getStatus())) {
            throw new BizException(403, "账号已被禁用");
        }
        String token = jwtUtils.createToken(user.getId(), user.getUsername());
        return new TokenResponse(token, String.valueOf(user.getId()), user.getUsername(), user.getRole(),
                user.getPointsBalance() == null ? BigDecimal.ZERO : user.getPointsBalance());
    }

    /**
     * 按用途发验证码，含快速失败的归属校验：
     * 注册场景要求邮箱未被注册；重置密码场景要求邮箱已注册。
     *
     * @param email 收件邮箱
     * @param scene 用途
     * @return 重发间隔秒数
     * @throws BizException 注册场景邮箱已存在（409）；重置场景邮箱未注册（400）
     */
    public long sendSceneCode(String email, MailCodeService.Scene scene) {
        String normalized = MailCodeService.normalize(email);
        boolean registered = userMapper.exists(
                new LambdaQueryWrapper<User>().eq(User::getEmail, normalized));
        if (scene == MailCodeService.Scene.REGISTER && registered) {
            throw new BizException(409, "该邮箱已被注册");
        }
        if (scene == MailCodeService.Scene.RESET && !registered) {
            throw new BizException(400, "该邮箱未注册");
        }
        return mailCodeService.sendCode(normalized, scene);
    }

    /**
     * 邮箱验证码重置密码（忘记密码）：验码（一次性，通过即销毁）→ 改 BCrypt 哈希。
     *
     * @param req 重置请求
     * @throws BizException 邮箱未注册（400）；验证码错误或已过期（400）
     */
    @Transactional
    public void resetPassword(ResetPasswordRequest req) {
        String email = MailCodeService.normalize(req.email());
        User user = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getEmail, email));
        if (user == null) {
            throw new BizException(400, "该邮箱未注册");
        }
        mailCodeService.verifyCode(email, req.code(), MailCodeService.Scene.RESET);
        user.setPasswordHash(passwordEncoder.encode(req.newPassword()));
        userMapper.updateById(user);
    }

    /**
     * 给新邮箱发绑定验证码：目标邮箱不能被任何账号占用
     *
     * @param userId 当前用户 ID
     * @param email  待绑定邮箱
     * @return 重发间隔秒数
     * @throws BizException 邮箱已是当前账号绑定邮箱（400）；被其他账号占用（409）
     */
    public long sendBindCode(Long userId, String email) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(404, "用户不存在");
        }
        String normalized = MailCodeService.normalize(email);
        if (normalized.equals(user.getEmail())) {
            throw new BizException(400, "该邮箱已是当前账号的绑定邮箱");
        }
        boolean used = userMapper.exists(
                new LambdaQueryWrapper<User>().eq(User::getEmail, normalized));
        if (used) {
            throw new BizException(409, "该邮箱已被其他账号绑定");
        }
        return mailCodeService.sendCode(normalized, MailCodeService.Scene.BIND);
    }

    /**
     * 凭验证码绑定邮箱：验码（一次性）→ 写 users.email（唯一索引兜底并发）
     *
     * @param userId 当前用户 ID
     * @param email  待绑定邮箱
     * @param code   6 位验证码（绑定场景）
     * @throws BizException 验证码错误或已过期（400）；邮箱被占用（409）
     */
    @Transactional
    public void bindEmail(Long userId, String email, String code) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(404, "用户不存在");
        }
        String normalized = MailCodeService.normalize(email);
        mailCodeService.verifyCode(normalized, code, MailCodeService.Scene.BIND);
        boolean used = userMapper.exists(
                new LambdaQueryWrapper<User>().eq(User::getEmail, normalized));
        if (used) {
            throw new BizException(409, "该邮箱已被其他账号绑定");
        }
        user.setEmail(normalized);
        try {
            userMapper.updateById(user);
        } catch (DuplicateKeyException e) {
            throw new BizException(409, "该邮箱已被其他账号绑定");
        }
    }

    /**
     * 给当前登录用户的绑定邮箱发验证码（改密码用）
     *
     * @param userId 当前用户 ID
     * @return 重发间隔秒数
     * @throws BizException 账号未绑定邮箱（400）；用户不存在（404）
     */
    public long sendMyCode(Long userId) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(404, "用户不存在");
        }
        if (user.getEmail() == null || user.getEmail().isBlank()) {
            throw new BizException(400, "账号未绑定邮箱，无法使用邮箱验证");
        }
        return mailCodeService.sendCode(user.getEmail(), MailCodeService.Scene.RESET);
    }

    /**
     * 已登录用户改密码（双模式，服务端按站长开关强制分流，前端传哪个不作数）：
     * 开启邮箱验证码功能 → 必须有绑定邮箱（前提）+ 邮箱验证码（凭证）；
     * 未开启 → 校验旧密码。
     *
     * @param userId 当前用户 ID
     * @param req    旧密码 / 验证码 / 新密码
     * @throws BizException 用户不存在（404）；未绑定邮箱（400）；验证码错误或旧密码错误（400）
     */
    @Transactional
    public void changePassword(Long userId, ChangePasswordRequest req) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(404, "用户不存在");
        }
        if (systemSettingService.isMailRegisterEnabled()) {
            // 邮箱是找回凭证的锚点：开启邮箱功能的站点，改密必须先绑定邮箱并持码验证
            if (user.getEmail() == null || user.getEmail().isBlank()) {
                throw new BizException(400, "请先绑定邮箱后再修改密码");
            }
            String code = req.code() == null ? "" : req.code().trim();
            mailCodeService.verifyCode(user.getEmail(), code, MailCodeService.Scene.RESET);
        } else {
            String oldPassword = req.oldPassword() == null ? "" : req.oldPassword();
            if (!passwordEncoder.matches(oldPassword, user.getPasswordHash())) {
                throw new BizException(400, "旧密码错误");
            }
        }
        user.setPasswordHash(passwordEncoder.encode(req.newPassword()));
        userMapper.updateById(user);
    }
}
