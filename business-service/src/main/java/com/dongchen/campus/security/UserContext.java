package com.dongchen.campus.security;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.domain.Role;

/**
 * 请求线程内的登录用户上下文。
 */
public final class UserContext {

    private static final ThreadLocal<CurrentUser> HOLDER = new ThreadLocal<>();

    private UserContext() {
    }

    public static void set(CurrentUser user) {
        HOLDER.set(user);
    }

    public static void clear() {
        HOLDER.remove();
    }

    public static CurrentUser get() {
        return HOLDER.get();
    }

    public static CurrentUser require() {
        CurrentUser user = HOLDER.get();
        if (user == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED, "未登录或登录已失效，请先登录");
        }
        return user;
    }

    public static long userId() {
        return require().userId();
    }

    public static Role role() {
        return require().role();
    }

    public static String classId() {
        return require().classId();
    }
}
