package com.spring.gateway.common;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * 时间格式化工具：数据库时间为 UTC。
 *
 * @author hanbing
 * @since 2026-10-03
 */
public final class TimeFormat {

    private static final DateTimeFormatter ISO_SECONDS = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    private TimeFormat() {
    }

    /**
     * UTC 时间转 ISO 格式字符串；
     * 微秒为 0 时省略小数部分，否则保留 6 位
     *
     * @param value naive UTC 时间，可为 null
     * @return ISO 字符串，value 为 null 时返回 null
     */
    public static String isoUtc(LocalDateTime value) {
        if (value == null) {
            return null;
        }
        StringBuilder text = new StringBuilder(value.format(ISO_SECONDS));
        int micros = value.getNano() / 1000;
        if (micros != 0) {
            text.append(String.format(".%06d", micros));
        }
        return text.append('Z').toString();
    }
}
