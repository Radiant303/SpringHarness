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
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

/**
 * sessions / messages 两表的数据面业务：MySQL 会话存储从 Python 引擎收敛到网关后，
 * Python 引擎经 /internal/** 内部 HTTP API 调用这里存取数据。
 *
 * <p>时间戳约定与 Python 侧一致：naive UTC（DATETIME 不带时区）。
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Service
@RequiredArgsConstructor
public class InternalStoreService {

    private final SessionMapper sessionMapper;
    private final MessageMapper messageMapper;
    private final ObjectMapper objectMapper;

    /**
     * 插入 sessions 行（current_segment=0, status=active）
     *
     * @param sessionId     会话 ID，由调用方生成
     * @param userId        所属用户 ID
     * @param workspacePath 工作区目录路径
     * @return 插入的会话行
     */
    public Session createSession(String sessionId, Long userId, String workspacePath) {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        Session session = new Session();
        session.setId(sessionId);
        session.setUserId(userId);
        session.setWorkspacePath(workspacePath);
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
     * 查询用户未删除的会话，按更新时间倒序（同秒时按 id 倒序保证确定性）
     *
     * @param userId 用户 ID
     * @return 会话行列表
     */
    public List<Session> listUserSessions(Long userId) {
        return sessionMapper.selectList(new LambdaQueryWrapper<Session>()
                .eq(Session::getUserId, userId)
                .ne(Session::getStatus, Session.STATUS_DELETED)
                .orderByDesc(Session::getUpdatedAt)
                .orderByDesc(Session::getId));
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

    private List<Message> selectMessages(String sessionId) {
        return messageMapper.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getSessionId, sessionId)
                .orderByAsc(Message::getSegmentNo)
                .orderByAsc(Message::getId));
    }

    private JsonNode readPayload(String payload) {
        try {
            return objectMapper.readTree(payload);
        } catch (Exception e) {
            throw new BizException(500, "消息 payload 解析失败: " + e.getMessage());
        }
    }
}
