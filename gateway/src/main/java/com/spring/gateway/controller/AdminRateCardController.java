package com.spring.gateway.controller;

import com.spring.gateway.common.RequiresOwner;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.AdminRateCardRequest;
import com.spring.gateway.dto.AdminRateCardView;
import com.spring.gateway.entity.RateCard;
import com.spring.gateway.service.AdminRateCardService;
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
 * 模型资费卡管理接口：查看对 owner/admin 开放，增删改仅站长。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@RestController
@RequestMapping("/api/admin/rate-cards")
@RequiredArgsConstructor
public class AdminRateCardController {

    private final AdminRateCardService adminRateCardService;

    /**
     * 资费卡列表（default 行置顶）
     *
     * @return 全部资费卡
     */
    @GetMapping
    public Result<List<AdminRateCardView>> list() {
        return Result.ok(adminRateCardService.list().stream().map(AdminRateCardController::toView).toList());
    }

    /**
     * 新建资费卡
     *
     * @param req 模型名与四项费率
     * @return 新建行
     */
    @RequiresOwner(message = "仅站长可管理模型资费")
    @PostMapping
    public Result<AdminRateCardView> create(@Valid @RequestBody AdminRateCardRequest req) {
        return Result.ok(toView(adminRateCardService.create(req)));
    }

    /**
     * 修改资费卡；兜底卡不可改名、不可停用
     *
     * @param id  资费卡 ID
     * @param req 新值
     * @return 空数据返回体
     */
    @RequiresOwner(message = "仅站长可管理模型资费")
    @PostMapping("/{id}")
    public Result<Void> update(@PathVariable Long id,
                               @Valid @RequestBody AdminRateCardRequest req) {
        adminRateCardService.update(id, req);
        return Result.ok(null);
    }

    /**
     * 删除资费卡；兜底卡不可删除
     *
     * @param id 资费卡 ID
     * @return 空数据返回体
     */
    @RequiresOwner(message = "仅站长可管理模型资费")
    @PostMapping("/{id}/delete")
    public Result<Void> delete(@PathVariable Long id) {
        adminRateCardService.delete(id);
        return Result.ok(null);
    }

    private static AdminRateCardView toView(RateCard row) {
        return new AdminRateCardView(
                String.valueOf(row.getId()),
                row.getModelName(),
                row.getInputPoints(),
                row.getCacheReadPoints(),
                row.getCacheWritePoints(),
                row.getOutputPoints(),
                row.getEnabled(),
                TimeFormat.isoUtc(row.getCreatedAt()),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }
}
