package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.service.PracticeService;
import com.dongchen.campus.web.dto.PracticeGenerateRequest;
import com.dongchen.campus.web.dto.PracticeHintRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/practice")
public class PracticeController {

    private final PracticeService practiceService;

    public PracticeController(PracticeService practiceService) {
        this.practiceService = practiceService;
    }

    @PostMapping("/generate")
    public ApiResponse<Map<String, Object>> generate(@RequestBody(required = false) PracticeGenerateRequest request) {
        String layer = request == null ? null : request.layer();
        Integer count = request == null ? null : request.count();
        java.util.List<String> kpIds = request == null ? null : request.kpIds();
        return ApiResponse.ok(practiceService.generate(layer, count, kpIds));
    }

    @PostMapping("/hint")
    public ApiResponse<Map<String, Object>> hint(@Valid @RequestBody PracticeHintRequest request) {
        return ApiResponse.ok(practiceService.hint(request.batchId(), request.questionId(), request.studentAnswer()));
    }
}
