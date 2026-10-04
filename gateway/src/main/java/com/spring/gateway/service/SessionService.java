package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.dto.SessionSummary;
import com.spring.gateway.entity.Session;
import com.spring.gateway.mapper.SessionMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;

/**
 * 会话业务：列表、详情、新建、删除。
 *
 * <p>写操作（新建、软删除）本地落库，读操作本地直查。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Service
public class SessionService {

    private final SessionMapper sessionMapper;
    private final InternalStoreService internalStoreService;
    private final String dataRoot;

    public SessionService(SessionMapper sessionMapper,
                          InternalStoreService internalStoreService,
                          @Value("${app.data-root}") String dataRoot) {
        this.sessionMapper = sessionMapper;
        this.internalStoreService = internalStoreService;
        this.dataRoot = dataRoot;
    }

    /**
     * 查询当前用户未删除的会话列表，按更新时间倒序
     *
     * @param userId 用户 ID
     * @return 会话摘要列表
     */
    public List<SessionSummary> list(Long userId) {
        List<Session> rows = sessionMapper.selectList(new LambdaQueryWrapper<Session>()
                .eq(Session::getUserId, userId)
                .ne(Session::getStatus, Session.STATUS_DELETED)
                .orderByDesc(Session::getUpdatedAt)
                .orderByDesc(Session::getId));
        return rows.stream().map(SessionService::toSummary).toList();
    }

    /**
     * 查询会话详情
     *
     * @param userId    用户 ID
     * @param sessionId 会话 ID
     * @return 会话摘要
     * @throws BizException 会话不存在、已删除或不属于当前用户（统一 404，不区分原因以防探测）
     */
    public SessionSummary detail(Long userId, String sessionId) {
        Session row = sessionMapper.selectOne(new LambdaQueryWrapper<Session>()
                .eq(Session::getId, sessionId)
                .eq(Session::getUserId, userId)
                .eq(Session::getStatus, Session.STATUS_ACTIVE));
        if (row == null) {
            throw new BizException(404, "会话不存在");
        }
        return toSummary(row);
    }

    /**
     * 新建会话：本地生成 UUID 与工作区路径后插入 sessions 行
     *
     * @param userId 当前用户 ID
     * @return 会话摘要
     */
    public SessionSummary create(Long userId) {
        String sessionId = UUID.randomUUID().toString();
        String workspacePath = dataRoot + "/workspaces/" + userId + "/" + sessionId;
        Session row = internalStoreService.createSession(sessionId, userId, workspacePath);
        return toSummary(row);
    }

    /**
     * 软删除会话（带归属校验）
     *
     * @param userId    当前用户 ID
     * @param sessionId 会话 ID
     * @throws BizException 会话不存在、不属于当前用户或已删除（统一 404）
     */
    public void delete(Long userId, String sessionId) {
        if (!internalStoreService.softDeleteSession(sessionId, userId)) {
            throw new BizException(404, "会话不存在");
        }
    }

    /** 转换为会话摘要 */
    private static SessionSummary toSummary(Session row) {
        return new SessionSummary(row.getId(), row.getTitle(), row.getCreatedAt(), row.getUpdatedAt());
    }
}
