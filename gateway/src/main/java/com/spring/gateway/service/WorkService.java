package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.entity.Message;
import com.spring.gateway.entity.Session;
import com.spring.gateway.entity.User;
import com.spring.gateway.entity.Work;
import com.spring.gateway.mapper.MessageMapper;
import com.spring.gateway.mapper.SessionMapper;
import com.spring.gateway.mapper.UserMapper;
import com.spring.gateway.mapper.WorkMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import java.util.stream.Stream;

/**
 * 项目（work）业务：列表、新建、默认项目、硬删除、容量统计。
 *
 * <p>硬删除会物理删除 {data-root}/works/{workId} 目录及库内全部关联行，删除前
 * 先询问引擎该 work 下有无活跃会话；引擎不可达时拒绝删除。
 *
 * @author hanbing
 * @since 2026-10-04
 */
@Service
@RequiredArgsConstructor
public class WorkService {

    /** 默认项目名。 */
    public static final String DEFAULT_WORK_NAME = "默认项目";

    private final WorkMapper workMapper;
    private final SessionMapper sessionMapper;
    private final MessageMapper messageMapper;
    private final UserMapper userMapper;
    private final EngineClient engineClient;

    @Value("${app.data-root}")
    private String dataRoot;

    @Value("${app.work-max-works:5}")
    private int maxWorks;

    /**
     * 当前用户的全部 work，返回前逐个重算目录占用并写回 size_bytes
     *
     * @param userId 用户 ID
     * @return work 列表，按创建时间倒序
     */
    public List<Work> list(Long userId) {
        List<Work> rows = workMapper.selectList(new LambdaQueryWrapper<Work>()
                .eq(Work::getUserId, userId)
                .orderByDesc(Work::getCreatedAt)
                .orderByDesc(Work::getId));
        for (Work row : rows) {
            row.setSizeBytes(refreshSize(row.getId()));
        }
        return rows;
    }

    /**
     * 新建 work；用户已有 work 数量达到上限、或全部 work 占用合计达到其存储配额时抛 409
     *
     * @param userId 用户 ID
     * @param name   项目名
     * @return 新建的 work
     * @throws BizException 超出数量上限或存储配额（409）
     */
    public Work create(Long userId, String name) {
        User user = requireUser(userId);
        Long count = workMapper.selectCount(new LambdaQueryWrapper<Work>().eq(Work::getUserId, userId));
        if (count >= maxWorks) {
            throw new BizException(409, "项目数量已达上限（" + maxWorks + "个），请先删除");
        }
        long used = workMapper.selectList(new LambdaQueryWrapper<Work>().eq(Work::getUserId, userId))
                .stream()
                .mapToLong(row -> row.getSizeBytes() == null ? 0L : row.getSizeBytes())
                .sum();
        long quota = user.getQuotaBytes() == null ? Long.MAX_VALUE : user.getQuotaBytes();
        if (used >= quota) {
            throw new BizException(409, "存储配额已用尽（" + used + "/" + quota + " 字节），请联系管理员调整");
        }
        return insert(userId, name, false);
    }

    /**
     * 确保用户存在默认 work，没有则创建；幂等，供内部接口与新建会话使用
     *
     * @param userId 用户 ID
     * @return 默认 work
     */
    public Work ensureDefault(Long userId) {
        requireUser(userId);
        Work existing = workMapper.selectOne(new LambdaQueryWrapper<Work>()
                .eq(Work::getUserId, userId)
                .eq(Work::getIsDefault, true));
        if (existing != null) {
            return existing;
        }
        return insert(userId, DEFAULT_WORK_NAME, true);
    }

    /**
     * 归属校验后取 work，不存在或属于他人一律 404
     *
     * @param userId 用户 ID
     * @param workId work ID
     * @return work 行
     * @throws BizException 不存在或越权（404）
     */
    public Work getOwned(Long userId, String workId) {
        Work row = workMapper.selectById(workId);
        if (row == null || !userId.equals(row.getUserId())) {
            throw new BizException(404, "项目不存在");
        }
        return row;
    }

    /**
     * 内部接口用：按 ID 取 work，不存在即 404（不做归属校验，调用方带 userId 入参自行校验）
     *
     * @param workId work ID
     * @return work 行
     * @throws BizException 不存在（404）
     */
    public Work getForInternal(String workId) {
        Work row = workMapper.selectById(workId);
        if (row == null) {
            throw new BizException(404, "项目不存在: " + workId);
        }
        return row;
    }

    /**
     * 硬删除 work：引擎有活跃会话（409）或引擎不可达（503）时拒绝；
     * 通过后删除消息、会话、work 行并物理删除目录
     *
     * @param userId 用户 ID
     * @param workId work ID
     * @throws BizException 越权（404）、有活跃会话（409）、引擎不可达（503）
     */
    @Transactional
    public void hardDelete(Long userId, String workId) {
        getOwned(userId, workId);
        int active;
        try {
            active = engineClient.activeSessionsInWork(workId);
        } catch (Exception e) {
            throw new BizException(503, "引擎不可达，拒绝删除");
        }
        if (active > 0) {
            throw new BizException(409, "项目下的会话正在使用中（页面挂载着该项目或有任务在跑），"
                    + "请先在页面切换到其他项目，或关闭对应标签页后再删除");
        }
        List<Session> sessions = sessionMapper.selectList(
                new LambdaQueryWrapper<Session>().eq(Session::getWorkId, workId));
        for (Session session : sessions) {
            messageMapper.delete(new LambdaQueryWrapper<Message>().eq(Message::getSessionId, session.getId()));
        }
        sessionMapper.delete(new LambdaQueryWrapper<Session>().eq(Session::getWorkId, workId));
        workMapper.deleteById(workId);
        deleteDirectoryRecursively(workspacePath(workId));
    }

    /**
     * 引擎上报的目录大小落库
     *
     * @param workId    work ID
     * @param sizeBytes 目录占用字节数
     */
    public void reportSize(String workId, long sizeBytes) {
        Work row = new Work();
        row.setId(workId);
        row.setSizeBytes(sizeBytes);
        workMapper.updateById(row);
    }

    /**
     * work 的派生工作区目录路径（路径权威在网关，引擎经内部 API 消费）
     *
     * @param workId work ID
     * @return 目录路径
     */
    public String workspacePath(String workId) {
        return dataRoot + "/works/" + workId;
    }

    /** 遍历目录求字节和；目录不存在视为 0 */
    private long refreshSize(String workId) {
        Path dir = Path.of(workspacePath(workId));
        if (!Files.isDirectory(dir)) {
            reportSize(workId, 0L);
            return 0L;
        }
        long total;
        try (Stream<Path> walk = Files.walk(dir)) {
            total = walk.filter(Files::isRegularFile)
                    .mapToLong(path -> {
                        try {
                            return Files.size(path);
                        } catch (IOException e) {
                            return 0L;
                        }
                    })
                    .sum();
        } catch (IOException e) {
            Work row = workMapper.selectById(workId);
            return row == null || row.getSizeBytes() == null ? 0L : row.getSizeBytes();
        }
        reportSize(workId, total);
        return total;
    }

    /** 用户不存在（库重建后旧 token 的幽灵用户）时拒绝，避免外键异常冒成 500 */
    private User requireUser(Long userId) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(404, "用户不存在");
        }
        return user;
    }

    private Work insert(Long userId, String name, boolean isDefault) {        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        Work row = new Work();
        row.setId(UUID.randomUUID().toString());
        row.setUserId(userId);
        row.setName(name);
        row.setSizeBytes(0L);
        row.setIsDefault(isDefault);
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        workMapper.insert(row);
        return row;
    }

    private static void deleteDirectoryRecursively(String dir) {
        Path root = Path.of(dir);
        if (!Files.exists(root)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(root)) {
            walk.sorted((a, b) -> -a.compareTo(b)).forEach(path -> {
                try {
                    Files.delete(path);
                } catch (IOException e) {
                    // 目录内被占用时尽力删，残留文件不阻断库内删除
                }
            });
        } catch (IOException ignored) {
            // 目录不存在或不可读：视为已删除
        }
    }
}
