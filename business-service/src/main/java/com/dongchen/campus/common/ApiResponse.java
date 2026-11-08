package com.dongchen.campus.common;

/**
 * 统一响应包装：{ success, message, data, code }。
 * 失败时 HTTP 状态码与 code 对应，见 {@link ErrorCode}。
 */
public record ApiResponse<T>(boolean success, String message, T data, String code) {

    public static <T> ApiResponse<T> ok(T data) {
        return new ApiResponse<>(true, "ok", data, null);
    }

    public static <T> ApiResponse<T> ok(String message, T data) {
        return new ApiResponse<>(true, message, data, null);
    }

    public static <T> ApiResponse<T> fail(ErrorCode code, String message) {
        return new ApiResponse<>(false, message, null, code == null ? null : code.name());
    }
}
