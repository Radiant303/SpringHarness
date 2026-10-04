package com.spring.gateway.common;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;

/**
 * 内部数据面接口鉴权拦截器：校验共享静态令牌 X-Internal-Token。
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Component
public class InternalAuthInterceptor implements HandlerInterceptor {

    /**
     * 存放内部令牌的请求头名
     */
    public static final String HEADER_TOKEN = "X-Internal-Token";

    private final String internalToken;
    private final ObjectMapper objectMapper;

    public InternalAuthInterceptor(@Value("${app.internal-token}") String internalToken,
                                   ObjectMapper objectMapper) {
        this.internalToken = internalToken;
        this.objectMapper = objectMapper;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws Exception {
        if (internalToken != null && internalToken.equals(request.getHeader(HEADER_TOKEN))) {
            return true;
        }
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(Result.error(401, "未认证")));
        return false;
    }
}
