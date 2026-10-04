package com.spring.gateway.controller;

import com.spring.gateway.common.BizException;
import com.spring.gateway.dto.InternalAppendMessagesRequest;
import com.spring.gateway.dto.InternalAppendResult;
import com.spring.gateway.dto.InternalCreateSessionRequest;
import com.spring.gateway.dto.InternalDeleteSessionRequest;
import com.spring.gateway.dto.InternalEnsureDefaultWorkRequest;
import com.spring.gateway.dto.InternalMessagePage;
import com.spring.gateway.dto.InternalReportWorkSizeRequest;
import com.spring.gateway.dto.InternalSessionSummary;
import com.spring.gateway.dto.InternalWorkSummary;
import com.spring.gateway.entity.Session;
import com.spring.gateway.entity.Work;
import com.spring.gateway.service.InternalStoreService;
import com.spring.gateway.service.WorkService;
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
 * 内部接口：会话与消息两表、work 的增查删，鉴权走共享静态令牌。
 *
 * <p>成功响应直接返回业务数据，不套统一返回体；错误仍走 BizException。</p>
 *
 * @author hanbing
 * @since 2026-10-03
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
public class InternalStoreController {

    private final InternalStoreService internalStoreService;
    private final WorkService workService;

    /**
     * 新建会话
     *
     * @param request 会话 ID、所属用户、所属 work
     * @return 会话摘要
     */
    @PostMapping("/sessions")
    public InternalSessionSummary createSession(@Valid @RequestBody InternalCreateSessionRequest request) {
        Session row = internalStoreService.createSession(
                request.sessionId(), request.userId(), request.workId());
        return InternalSessionSummary.from(row, internalStoreService.workspacePath(row.getWorkId()));
    }

    /**
     * 查询会话摘要（含 workId、派生工作区路径、当前段号、状态）
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
        return InternalSessionSummary.from(row, internalStoreService.workspacePath(row.getWorkId()));
    }

    /**
     * 查询某用户的会话摘要列表
     *
     * @param userId 用户 ID
     * @return 会话摘要列表
     */
    @GetMapping("/users/{userId}/sessions")
    public List<InternalSessionSummary> listUserSessions(@PathVariable Long userId) {
        return internalStoreService.listUserSessions(userId, null).stream()
                .map(row -> InternalSessionSummary.from(row, internalStoreService.workspacePath(row.getWorkId())))
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

    /**
     * 查询 work 详情（含派生工作区路径），不存在即 404
     *
     * @param workId work ID
     * @return work 摘要
     */
    @GetMapping("/works/{workId}")
    public InternalWorkSummary getWork(@PathVariable String workId) {
        Work row = workService.getForInternal(workId);
        return InternalWorkSummary.from(row, workService.workspacePath(workId));
    }

    /**
     * 确保用户存在默认 work，没有则创建（幂等）
     *
     * @param request 用户 ID
     * @return work 摘要
     */
    @PostMapping("/works/default")
    public InternalWorkSummary ensureDefaultWork(@Valid @RequestBody InternalEnsureDefaultWorkRequest request) {
        Work row = workService.ensureDefault(request.userId());
        return InternalWorkSummary.from(row, workService.workspacePath(row.getId()));
    }

    /**
     * 引擎上报 work 目录占用字节数
     *
     * @param workId  work ID
     * @param request 占用字节数
     */
    @PostMapping("/works/{workId}/size")
    public void reportWorkSize(@PathVariable String workId,
                               @Valid @RequestBody InternalReportWorkSizeRequest request) {
        workService.getForInternal(workId);
        workService.reportSize(workId, request.sizeBytes());
    }
}
