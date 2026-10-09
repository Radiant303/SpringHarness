package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.JwtUtils;
import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.dto.LoginRequest;
import com.spring.gateway.dto.RegisterRequest;
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
            mailCodeService.verifyCode(email, code);
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
}
