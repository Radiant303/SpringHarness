package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.Result;
import com.spring.gateway.dto.SessionSummary;
import com.spring.gateway.service.SessionService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 会话接口
 *
 * @author hanbing
 * @since 2026-09-26
 */
@RestController
@RequestMapping("/api/sessions")
@RequiredArgsConstructor
public class SessionController {

    private final SessionService sessionService;

    /**
     * 会话列表
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @return 会话摘要列表
     */
    @GetMapping
    public Result<List<SessionSummary>> list(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        return Result.ok(sessionService.list(userId));
    }

    /**
     * 会话详情
     *
     * @param userId    当前用户 ID
     * @param sessionId 会话 ID
     * @return 会话摘要
     */
    @GetMapping("/{sessionId}")
    public Result<SessionSummary> detail(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                                         @PathVariable String sessionId) {
        return Result.ok(sessionService.detail(userId, sessionId));
    }

    /**
     * 新建会话（网关本地落库）
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @return 会话摘要
     */
    @PostMapping
    public Result<SessionSummary> create(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        return Result.ok(sessionService.create(userId));
    }

    /**
     * 删除会话（网关本地软删除）
     *
     * @param sessionId 会话 ID
     * @param userId    当前用户 ID（拦截器注入）
     * @return 空数据返回体
     */
    @DeleteMapping("/{sessionId}")
    public Result<Void> delete(@PathVariable String sessionId,
                               @RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        sessionService.delete(userId, sessionId);
        return Result.ok(null);
    }
}
