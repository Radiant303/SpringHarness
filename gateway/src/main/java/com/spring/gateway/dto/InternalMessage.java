package com.spring.gateway.dto;

import tools.jackson.databind.JsonNode;

/**
 * 一条历史消息：段号 + payload 原文（JSON 列内容，网关不解析其结构）。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param segmentNo 段号
 * @param payload   消息 JSON 原文
 */
public record InternalMessage(Integer segmentNo, JsonNode payload) {
}
