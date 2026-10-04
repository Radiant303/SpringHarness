package com.spring.gateway.dto;

import java.util.List;

/**
 * 会话全部消息：当前段号 + 按 (segment_no, id) 升序的消息列表。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param currentSegment 当前段号，会话行不存在时为 0
 * @param messages       消息列表
 */
public record InternalMessagePage(Integer currentSegment, List<InternalMessage> messages) {
}
