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

/**
 * 认证业务：用户注册与登录。
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

    /**
     * 注册新用户
     *
     * @param req 注册请求
     * @return 用户信息
     * @throws BizException 用户名已存在（409）
     */
    public UserResponse register(RegisterRequest req) {
        boolean exists = userMapper.exists(
                new LambdaQueryWrapper<User>().eq(User::getUsername, req.username()));
        if (exists) {
            throw new BizException(409, "用户名已存在");
        }
        User user = new User();
        user.setId(idGenerator.nextId());
        user.setUsername(req.username());
        user.setPasswordHash(passwordEncoder.encode(req.password()));
        try {
            userMapper.insert(user);
        } catch (DuplicateKeyException e) {
            // 先查后插存在并发窗口，由 username 唯一索引兜底；并发冲突时同样按用户名已存在处理
            throw new BizException(409, "用户名已存在");
        }
        return new UserResponse(user.getId(), user.getUsername());
    }

    /**
     * 登录并签发 JWT
     *
     * @param req 登录请求
     * @return token 与用户信息
     * @throws BizException 用户名不存在或密码错误（401，两种情况返回相同信息以避免用户名枚举）
     */
    public TokenResponse login(LoginRequest req) {
        User user = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getUsername, req.username()));
        if (user == null || !passwordEncoder.matches(req.password(), user.getPasswordHash())) {
            throw new BizException(401, "用户名或密码错误");
        }
        String token = jwtUtils.createToken(user.getId(), user.getUsername());
        return new TokenResponse(token, user.getId(), user.getUsername());
    }
}
