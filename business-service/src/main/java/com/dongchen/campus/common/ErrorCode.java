package com.dongchen.campus.common;

/**
 * 业务错误码，与 docs/01-接口约定.md 3.1 一致。
 */
public enum ErrorCode {
    UNAUTHORIZED(401),
    FORBIDDEN(403),
    NOT_FOUND(404),
    VALIDATION_ERROR(400),
    CONFLICT(409),
    AI_UNAVAILABLE(503),
    INTERNAL_ERROR(500);

    private final int httpStatus;

    ErrorCode(int httpStatus) {
        this.httpStatus = httpStatus;
    }

    public int httpStatus() {
        return httpStatus;
    }
}
