package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.service.AuthService;
import com.dongchen.campus.web.dto.LoginRequest;
import com.dongchen.campus.web.dto.PasswordRequest;
import com.dongchen.campus.web.dto.ProfileRequest;
import com.dongchen.campus.web.dto.RegisterRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/auth/login")
    public ApiResponse<Map<String, Object>> login(@Valid @RequestBody LoginRequest request) {
        return ApiResponse.ok(authService.login(request.username(), request.password()));
    }

    /** v1.4 学生注册（公开接口，注册即登录）。 */
    @PostMapping("/auth/register")
    public ApiResponse<Map<String, Object>> register(@Valid @RequestBody RegisterRequest request) {
        return ApiResponse.ok(authService.register(request.username(), request.password(),
                request.displayName(), request.email()));
    }

    @GetMapping("/auth/me")
    public ApiResponse<Map<String, Object>> me() {
        return ApiResponse.ok(authService.me());
    }

    @PostMapping("/auth/logout")
    public ApiResponse<Void> logout() {
        return ApiResponse.ok(null);
    }

    @PutMapping("/auth/password")
    public ApiResponse<Void> changePassword(@Valid @RequestBody PasswordRequest request) {
        authService.changePassword(request.oldPassword(), request.newPassword());
        return ApiResponse.ok(null);
    }

    @PutMapping("/users/me")
    public ApiResponse<Map<String, Object>> updateProfile(@RequestBody ProfileRequest request) {
        return ApiResponse.ok(authService.updateProfile(request.displayName(), request.email(),
                request.phone(), request.targetSchool(), request.examYear()));
    }
}
