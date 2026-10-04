package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.CreateWorkRequest;
import com.spring.gateway.dto.WorkSummary;
import com.spring.gateway.entity.Work;
import com.spring.gateway.service.WorkService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 项目（work）接口
 *
 * @author hanbing
 * @since 2026-10-04
 */
@RestController
@RequestMapping("/api/works")
@RequiredArgsConstructor
public class WorkController {

    private final WorkService workService;

    /**
     * 项目列表（size_bytes 为刚重算的最新值）
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @return work 摘要列表
     */
    @GetMapping
    public Result<List<WorkSummary>> list(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        return Result.ok(workService.list(userId).stream().map(WorkController::toSummary).toList());
    }

    /**
     * 新建项目；达到数量上限返回 409
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @param req    项目名
     * @return work 摘要
     */
    @PostMapping
    public Result<WorkSummary> create(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                                      @Valid @RequestBody CreateWorkRequest req) {
        return Result.ok(toSummary(workService.create(userId, req.name())));
    }

    /**
     * 硬删除项目：删除目录及全部关联数据，有活跃会话或引擎不可达时拒绝
     *
     * @param userId 当前用户 ID（拦截器注入）
     * @param workId work ID
     * @return 空数据返回体
     */
    @DeleteMapping("/{workId}")
    public Result<Void> delete(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                               @PathVariable String workId) {
        workService.hardDelete(userId, workId);
        return Result.ok(null);
    }

    private static WorkSummary toSummary(Work row) {
        return new WorkSummary(
                row.getId(),
                row.getName(),
                row.getSizeBytes() == null ? 0L : row.getSizeBytes(),
                Boolean.TRUE.equals(row.getIsDefault()),
                TimeFormat.isoUtc(row.getCreatedAt()),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }
}
