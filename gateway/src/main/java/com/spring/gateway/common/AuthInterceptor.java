package com.spring.gateway.common;

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
 * 会话接口鉴权拦截器：校验 Bearer token，通过后把用户 ID 存入请求属性。
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

    private final JwtUtils jwtUtils;
    private final ObjectMapper objectMapper;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws Exception {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header != null && header.startsWith("Bearer ")) {
            Long userId = jwtUtils.parseUserId(header.substring(7));
            if (userId != null) {
                request.setAttribute(ATTR_USER_ID, userId);
                return true;
            }
        }
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(Result.error(401, "未认证")));
        return false;
    }
}
