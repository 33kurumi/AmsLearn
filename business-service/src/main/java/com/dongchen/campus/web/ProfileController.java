package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.service.ProfileAiService;
import com.dongchen.campus.web.dto.AiProfileRequest;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * v1.2 个人 AI 配置：只回掩码，Key 加密存储。
 */
@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private final ProfileAiService profileAiService;

    public ProfileController(ProfileAiService profileAiService) {
        this.profileAiService = profileAiService;
    }

    @GetMapping("/ai")
    public ApiResponse<Map<String, Object>> getAiConfig() {
        return ApiResponse.ok(profileAiService.get());
    }

    @PutMapping("/ai")
    public ApiResponse<Map<String, Object>> updateAiConfig(@RequestBody AiProfileRequest request) {
        return ApiResponse.ok(profileAiService.update(request.apiKey(), request.baseUrl(),
                request.model(), request.enabled()));
    }

    @DeleteMapping("/ai")
    public ApiResponse<Map<String, Object>> clearAiConfig() {
        return ApiResponse.ok(profileAiService.clear());
    }
}
