package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.dto.InternalAppendResult;
import com.spring.gateway.dto.InternalMessage;
import com.spring.gateway.dto.InternalMessagePage;
import com.spring.gateway.entity.Message;
import com.spring.gateway.entity.Session;
import com.spring.gateway.mapper.MessageMapper;
import com.spring.gateway.mapper.SessionMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

/**
 * sessions / messages 两表的读写服务，供内部接口调用。
 *
 * <p>会话摘要里的 workspacePath 由所属 work 派生（{data-root}/works/{workId}），
 * 路径权威在本服务。时间戳统一使用 UTC。
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Service
@RequiredArgsConstructor
public class InternalStoreService {

    private final SessionMapper sessionMapper;
    private final MessageMapper messageMapper;
    private final WorkService workService;
    private final ObjectMapper objectMapper;

    @Value("${app.data-root}")
    private String dataRoot;

    /**
     * 插入 sessions 行（current_segment=0, status=active）；work 不存在或归属不符抛 404
     *
     * @param sessionId 会话 ID，由调用方生成
     * @param userId    所属用户 ID
     * @param workId    所属 work ID
     * @return 插入的会话行
     * @throws BizException work 不存在或不属于该用户（404）
     */
    public Session createSession(String sessionId, Long userId, String workId) {
        workService.getOwned(userId, workId);
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        Session session = new Session();
        session.setId(sessionId);
        session.setUserId(userId);
        session.setWorkId(workId);
        session.setCurrentSegment(0);
        session.setStatus(Session.STATUS_ACTIVE);
        session.setCreatedAt(now);
        session.setUpdatedAt(now);
        sessionMapper.insert(session);
        return session;
    }

    /**
     * 查询会话行
     *
     * @param sessionId 会话 ID
     * @return 会话行，不存在返回 null
     */
    public Session getSession(String sessionId) {
        return sessionMapper.selectById(sessionId);
    }

    /**
     * 查询用户未删除的会话，按更新时间倒序（同秒时按 id 倒序保证确定性）；
     * workId 非 null 时只返回该 work 下的会话
     *
     * @param userId 用户 ID
     * @param workId work ID，可为 null
     * @return 会话行列表
     */
    public List<Session> listUserSessions(Long userId, String workId) {
        LambdaQueryWrapper<Session> query = new LambdaQueryWrapper<Session>()
                .eq(Session::getUserId, userId)
                .ne(Session::getStatus, Session.STATUS_DELETED)
                .orderByDesc(Session::getUpdatedAt)
                .orderByDesc(Session::getId);
        if (workId != null) {
            query.eq(Session::getWorkId, workId);
        }
        return sessionMapper.selectList(query);
    }

    /**
     * 查询会话全部消息（按 segment_no, id 升序）与当前段号
     *
     * @param sessionId 会话 ID
     * @return 当前段号 + 消息列表；会话行不存在时当前段号为 0、消息为空
     */
    public InternalMessagePage getMessages(String sessionId) {
        Session row = sessionMapper.selectById(sessionId);
        if (row == null) {
            return new InternalMessagePage(0, List.of());
        }
        List<Message> rows = selectMessages(sessionId);
        List<InternalMessage> messages = new ArrayList<>(rows.size());
        for (Message item : rows) {
            messages.add(new InternalMessage(item.getSegmentNo(), readPayload(item.getPayload())));
        }
        return new InternalMessagePage(row.getCurrentSegment(), messages);
    }

    /**
     * 追加消息：newSegment 时先开新段，title 仅在会话行标题为空时写入
     *
     * @param sessionId  会话 ID
     * @param newSegment 是否开新段（current_segment 自增）
     * @param title      会话标题，可为 null
     * @param messages   消息 JSON 列表
     * @return 追加条数与写入的段号
     * @throws BizException 会话不存在（404）
     */
    @Transactional
    public InternalAppendResult appendMessages(String sessionId, boolean newSegment, String title,
                                              List<JsonNode> messages) {
        Session row = sessionMapper.selectById(sessionId);
        if (row == null) {
            throw new BizException(404, "会话不存在: " + sessionId);
        }
        int segmentNo = newSegment ? row.getCurrentSegment() + 1 : row.getCurrentSegment();
        List<Message> rows = new ArrayList<>(messages.size());
        for (JsonNode message : messages) {
            Message item = new Message();
            item.setSessionId(sessionId);
            item.setSegmentNo(segmentNo);
            item.setPayload(objectMapper.writeValueAsString(message));
            rows.add(item);
        }
        if (!rows.isEmpty()) {
            messageMapper.insert(rows, 500);
        }
        row.setCurrentSegment(segmentNo);
        row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        if (title != null && row.getTitle() == null) {
            row.setTitle(title);
        }
        sessionMapper.updateById(row);
        return new InternalAppendResult(rows.size(), segmentNo);
    }

    /**
     * 软删除会话：status 置 deleted 并推进 updated_at
     *
     * @param sessionId 会话 ID
     * @param userId    发起删除的用户 ID
     * @return 行不存在 / 不属于该用户 / 已删除时返回 false，否则 true
     */
    public boolean softDeleteSession(String sessionId, Long userId) {
        Session row = sessionMapper.selectById(sessionId);
        if (row == null || !userId.equals(row.getUserId()) || Session.STATUS_DELETED.equals(row.getStatus())) {
            return false;
        }
        row.setStatus(Session.STATUS_DELETED);
        row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        sessionMapper.updateById(row);
        return true;
    }

    /**
     * 会话摘要里派生的工作区目录路径
     *
     * @param workId work ID
     * @return 目录路径
     */
    public String workspacePath(String workId) {
        return workService.workspacePath(workId);
    }

    /** 按段号、主键升序查询会话的全部消息 */
    private List<Message> selectMessages(String sessionId) {
        return messageMapper.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getSessionId, sessionId)
                .orderByAsc(Message::getSegmentNo)
                .orderByAsc(Message::getId));
    }

    /** 解析消息 payload，失败抛 500 */
    private JsonNode readPayload(String payload) {
        try {
            return objectMapper.readTree(payload);
        } catch (Exception e) {
            throw new BizException(500, "消息 payload 解析失败: " + e.getMessage());
        }
    }
}
