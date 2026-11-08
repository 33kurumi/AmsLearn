package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.service.HealthService;
import com.dongchen.campus.service.MetaService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class MetaController {

    private final HealthService healthService;
    private final MetaService metaService;

    public MetaController(HealthService healthService, MetaService metaService) {
        this.healthService = healthService;
        this.metaService = metaService;
    }

    @GetMapping("/health")
    public ApiResponse<Map<String, Object>> health() {
        return ApiResponse.ok(healthService.health());
    }

    @GetMapping("/meta/knowledge-points")
    public ApiResponse<List<Map<String, Object>>> knowledgePoints() {
        return ApiResponse.ok(metaService.knowledgePoints());
    }

    @GetMapping("/meta/dictionaries")
    public ApiResponse<Map<String, Object>> dictionaries() {
        return ApiResponse.ok(metaService.dictionaries());
    }
}
