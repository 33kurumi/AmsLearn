package com.dongchen.campus.common;

/**
 * 业务异常：携带契约错误码与 HTTP 状态码。
 */
public class BusinessException extends RuntimeException {

    private final ErrorCode code;
    private final int httpStatus;

    public BusinessException(ErrorCode code, String message) {
        this(code, message, code.httpStatus());
    }

    public BusinessException(ErrorCode code, String message, int httpStatus) {
        super(message);
        this.code = code;
        this.httpStatus = httpStatus;
    }

    public ErrorCode getCode() {
        return code;
    }

    public int getHttpStatus() {
        return httpStatus;
    }
}
