package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.dto.SessionSummary;
import com.spring.gateway.entity.Session;
import com.spring.gateway.mapper.SessionMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

import java.util.List;

/**
 * 会话业务：列表、详情、新建、删除、历史分页。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Service
@RequiredArgsConstructor
public class SessionService {

    private final SessionMapper sessionMapper;
    private final EngineClient engineClient;

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
     * 新建会话
     *
     * @param authorization 原始 Authorization 头
     * @return 会话摘要
     */
    public JsonNode create(String authorization) {
        return engineClient.createSession(authorization);
    }

    /**
     * 删除会话
     *
     * @param sessionId     会话 ID
     * @param authorization 原始 Authorization 头
     */
    public void delete(String sessionId, String authorization) {
        engineClient.deleteSession(sessionId, authorization);
    }

    /**
     * 查询会话历史分页
     *
     * @param sessionId     会话 ID
     * @param cursor        分页游标，可为 null
     * @param limit         每页消息数
     * @param direction     翻页方向
     * @param authorization 原始 Authorization 头
     * @return 历史分页
     */
    public JsonNode history(String sessionId, String cursor, int limit, String direction,
                            String authorization) {
        return engineClient.history(sessionId, cursor, limit, direction, authorization);
    }

    private static SessionSummary toSummary(Session row) {
        return new SessionSummary(row.getId(), row.getTitle(), row.getCreatedAt(), row.getUpdatedAt());
    }
}
