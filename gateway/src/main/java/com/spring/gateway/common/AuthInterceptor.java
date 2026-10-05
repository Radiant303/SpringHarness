package com.spring.gateway.common;

import com.spring.gateway.entity.User;
import com.spring.gateway.mapper.UserMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;

/**
 * 会话接口鉴权拦截器：校验 Bearer token 并按用户行实时收口权限。
 *
 * <p>角色权威在数据库（不进 JWT）：每次请求按 sub 主键查一次 users 行——
 * 禁用账号、调整角色立即生效，不必等 token 过期。通过后把用户 ID 与角色存入请求属性；
 * /api/admin/** 路径在此统一要求 owner/admin 角色。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Component
@RequiredArgsConstructor
public class AuthInterceptor implements HandlerInterceptor {

    /**
     * 存放用户 ID 的请求属性名
     */
    public static final String ATTR_USER_ID = "userId";

    /**
     * 存放用户角色（owner/admin/user）的请求属性名
     */
    public static final String ATTR_USER_ROLE = "userRole";

    /** 管理接口路径前缀：仅站长/管理员可访问 */
    private static final String ADMIN_PATH_PREFIX = "/api/admin/";

    private final JwtUtils jwtUtils;
    private final UserMapper userMapper;
    private final ObjectMapper objectMapper;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws Exception {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header != null && header.startsWith("Bearer ")) {
            Long userId = jwtUtils.parseUserId(header.substring(7));
            if (userId != null) {
                User user = userMapper.selectById(userId);
                if (user == null) {
                    reject(response, HttpStatus.UNAUTHORIZED, "未认证");
                    return false;
                }
                if (User.STATUS_DISABLED.equals(user.getStatus())) {
                    reject(response, HttpStatus.FORBIDDEN, "账号已被禁用");
                    return false;
                }
                if (request.getRequestURI().startsWith(ADMIN_PATH_PREFIX)
                        && !User.ROLE_OWNER.equals(user.getRole())
                        && !User.ROLE_ADMIN.equals(user.getRole())) {
                    reject(response, HttpStatus.FORBIDDEN, "无权限");
                    return false;
                }
                request.setAttribute(ATTR_USER_ID, userId);
                request.setAttribute(ATTR_USER_ROLE, user.getRole());
                return true;
            }
        }
        reject(response, HttpStatus.UNAUTHORIZED, "未认证");
        return false;
    }

    private void reject(HttpServletResponse response, HttpStatus status, String message) throws Exception {
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(Result.error(status.value(), message)));
    }
}
