package com.spring.gateway.common;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 站长专属接口：标注在 Controller 方法上，由 AuthInterceptor 统一校验——
 * 角色权威在数据库，拦截器查用户行后顺手完成判断，非站长访问直接 403。
 * 方法体内不再重复 if/throw，漏标注解比漏写 if 更容易在评审中发现。
 *
 * @author hanbing
 * @since 2026-10-11
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RequiresOwner {

    /** 拒绝时的错误信息 */
    String message() default "仅站长可执行此操作";
}
