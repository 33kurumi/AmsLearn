package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.service.DiagnoseService;
import com.dongchen.campus.web.dto.DiagnoseStartRequest;
import com.dongchen.campus.web.dto.DiagnoseSubmitRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/diagnose")
public class DiagnoseController {

    private final DiagnoseService diagnoseService;

    public DiagnoseController(DiagnoseService diagnoseService) {
        this.diagnoseService = diagnoseService;
    }

    @PostMapping("/start")
    public ApiResponse<Map<String, Object>> start(@RequestBody(required = false) DiagnoseStartRequest request) {
        String mode = request == null ? null : request.mode();
        List<String> focusKpIds = request == null ? null : request.focusKpIds();
        return ApiResponse.ok(diagnoseService.start(mode, focusKpIds));
    }

    @PostMapping("/{sessionId}/submit")
    public ApiResponse<Map<String, Object>> submit(@PathVariable Long sessionId,
                                                   @Valid @RequestBody DiagnoseSubmitRequest request) {
        List<Map<String, Object>> answers = new ArrayList<>();
        for (DiagnoseSubmitRequest.Answer answer : request.answers()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("questionId", answer.questionId());
            item.put("answer", answer.answer());
            answers.add(item);
        }
        return ApiResponse.ok(diagnoseService.submit(sessionId, answers));
    }
}
