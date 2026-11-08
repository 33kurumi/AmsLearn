package com.dongchen.campus.security;

import com.dongchen.campus.domain.Role;

/**
 * 当前登录用户上下文快照。
 */
public record CurrentUser(long userId, Role role, String classId) {
}
