package com.spring.gateway.dto;

/**
 * 追加消息的结果。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param appended  实际追加的消息条数
 * @param segmentNo 消息写入的段号
 */
public record InternalAppendResult(int appended, int segmentNo) {
}
