package com.spring.gateway.controller;

import com.spring.gateway.common.BizException;
import com.spring.gateway.dto.InternalAppendMessagesRequest;
import com.spring.gateway.dto.InternalAppendResult;
import com.spring.gateway.dto.InternalCreateSessionRequest;
import com.spring.gateway.dto.InternalDeleteSessionRequest;
import com.spring.gateway.dto.InternalMessagePage;
import com.spring.gateway.dto.InternalSessionSummary;
import com.spring.gateway.entity.Session;
import com.spring.gateway.service.InternalStoreService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 内部数据面接口：Python 引擎经这些端点读写 sessions / messages 两表，
 * 鉴权走共享静态令牌（X-Internal-Token），与用户 JWT 无关。
 *
 * <p>MySQL 会话存储收敛到网关后，引擎不再直连数据库；网关不跑引擎逻辑，
 * 只把两表的增查删原样暴露给引擎。</p>
 *
 * <p>成功响应体是业务数据本身（不套 /api 的统一返回体）：Python 侧 httpx client
 * 直接 {@code response.json()} 按字段消费；错误仍走 BizException
 * （404 时 Python 侧按"不存在"处理）。</p>
 *
 * @author hanbing
 * @since 2026-10-03
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalStoreController {

    private final InternalStoreService internalStoreService;

    /**
     * 新建会话
     *
     * @param request 会话 ID、所属用户、工作区路径
     * @return 会话摘要
     */
    @PostMapping("/sessions")
    public InternalSessionSummary createSession(@Valid @RequestBody InternalCreateSessionRequest request) {
        Session row = internalStoreService.createSession(
                request.sessionId(), request.userId(), request.workspacePath());
        return InternalSessionSummary.from(row);
    }

    /**
     * 查询会话摘要（含当前段号、状态、工作区路径）
     *
     * @param sessionId 会话 ID
     * @return 会话摘要
     */
    @GetMapping("/sessions/{sessionId}")
    public InternalSessionSummary getSession(@PathVariable String sessionId) {
        Session row = internalStoreService.getSession(sessionId);
        if (row == null) {
            throw new BizException(404, "会话不存在: " + sessionId);
        }
        return InternalSessionSummary.from(row);
    }

    /**
     * 查询某用户的会话摘要列表
     *
     * @param userId 用户 ID
     * @return 会话摘要列表
     */
    @GetMapping("/users/{userId}/sessions")
    public List<InternalSessionSummary> listUserSessions(@PathVariable Long userId) {
        return internalStoreService.listUserSessions(userId).stream()
                .map(InternalSessionSummary::from)
                .toList();
    }

    /**
     * 查询会话全部消息（payload 为 JSON 原文）
     *
     * @param sessionId 会话 ID
     * @return 当前段号 + 消息列表
     */
    @GetMapping("/sessions/{sessionId}/messages")
    public InternalMessagePage getMessages(@PathVariable String sessionId) {
        return internalStoreService.getMessages(sessionId);
    }

    /**
     * 追加消息：newSegment 时先开新段，title 仅在会话行标题为空时写入
     *
     * @param sessionId 会话 ID
     * @param request   追加参数
     * @return 追加条数与写入的段号
     */
    @PostMapping("/sessions/{sessionId}/messages")
    public InternalAppendResult appendMessages(@PathVariable String sessionId,
                                               @Valid @RequestBody InternalAppendMessagesRequest request) {
        return internalStoreService.appendMessages(
                sessionId, Boolean.TRUE.equals(request.newSegment()), request.title(), request.messages());
    }

    /**
     * 软删除会话（带归属校验）
     *
     * @param sessionId 会话 ID
     * @param request   发起删除的用户 ID
     */
    @PostMapping("/sessions/{sessionId}/delete")
    public void deleteSession(@PathVariable String sessionId,
                              @Valid @RequestBody InternalDeleteSessionRequest request) {
        if (!internalStoreService.softDeleteSession(sessionId, request.userId())) {
            throw new BizException(404, "会话不存在: " + sessionId);
        }
    }
}
