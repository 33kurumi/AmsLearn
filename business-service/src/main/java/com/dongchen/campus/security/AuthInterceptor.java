package com.dongchen.campus.security;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.domain.Role;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.nio.charset.StandardCharsets;

/**
 * /api/** 鉴权拦截器：校验 Bearer 令牌、按前缀做角色校验。
 * 放行：/api/health、/api/auth/login、/api/auth/register、OPTIONS 预检。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    private final TokenService tokenService;
    private final UserRepository userRepository;
    private final ObjectMapper objectMapper;

    public AuthInterceptor(TokenService tokenService, UserRepository userRepository, ObjectMapper objectMapper) {
        this.tokenService = tokenService;
        this.userRepository = userRepository;
        this.objectMapper = objectMapper;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }
        String uri = request.getRequestURI();
        if (uri.equals("/api/health") || uri.equals("/api/auth/login")
                || uri.equals("/api/auth/register")) {
            return true;
        }

        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ") || header.length() <= 7) {
            writeError(response, ErrorCode.UNAUTHORIZED, "未登录或登录已失效，请先登录");
            return false;
        }

        TokenService.Payload payload;
        try {
            payload = tokenService.verify(header.substring(7).trim());
        } catch (BusinessException ex) {
            writeError(response, ex.getCode(), ex.getMessage());
            return false;
        }

        UserInfo user = userRepository.findById(payload.userId()).orElse(null);
        if (user == null) {
            writeError(response, ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录");
            return false;
        }

        Role role = user.getRole();
        if (requiresStudent(uri) && role != Role.STUDENT) {
            writeError(response, ErrorCode.FORBIDDEN, "无权访问该资源");
            return false;
        }
        if (uri.startsWith("/api/teacher/") && role != Role.TEACHER) {
            writeError(response, ErrorCode.FORBIDDEN, "无权访问该资源");
            return false;
        }

        UserContext.set(new CurrentUser(user.getId(), role, user.getClassId()));
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        UserContext.clear();
    }

    private boolean requiresStudent(String uri) {
        return uri.startsWith("/api/student/")
                || uri.startsWith("/api/conversations")
                || uri.equals("/api/chat")
                || uri.startsWith("/api/diagnose/")
                || uri.startsWith("/api/practice/")
                || uri.startsWith("/api/plans");
    }

    private void writeError(HttpServletResponse response, ErrorCode code, String message) throws Exception {
        response.setStatus(code.httpStatus());
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        objectMapper.writeValue(response.getWriter(), ApiResponse.fail(code, message));
    }
}
