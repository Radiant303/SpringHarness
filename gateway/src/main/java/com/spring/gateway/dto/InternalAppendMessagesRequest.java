package com.spring.gateway.dto;

import jakarta.validation.constraints.NotNull;
import tools.jackson.databind.JsonNode;

import java.util.List;

/**
 * 内部 API：追加消息请求。messages 为消息 JSON 原文列表，网关不解析其结构。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param newSegment true 表示先开新段（current_segment 自增）再整体写入
 * @param title      会话标题，仅当会话行 title 为空时写入，可为 null
 * @param messages   待追加的消息 JSON 列表
 */
public record InternalAppendMessagesRequest(
        Boolean newSegment,

        String title,

        @NotNull(message = "messages 不能为空")
        List<JsonNode> messages
) {
}
