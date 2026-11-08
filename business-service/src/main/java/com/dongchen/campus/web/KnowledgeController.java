package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.service.KnowledgeService;
import com.dongchen.campus.web.dto.KnowledgeToggleRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

@RestController
@RequestMapping("/api/teacher/knowledge")
public class KnowledgeController {

    private final KnowledgeService knowledgeService;

    public KnowledgeController(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
    }

    @GetMapping
    public ApiResponse<Map<String, Object>> documents() {
        return ApiResponse.ok(knowledgeService.documents());
    }

    @PostMapping("/upload")
    public ApiResponse<Map<String, Object>> upload(@RequestParam("file") MultipartFile file,
                                                   @RequestParam(value = "kb", required = false) String kb) {
        return ApiResponse.ok(knowledgeService.upload(file, kb));
    }

    @PatchMapping("/{documentId}")
    public ApiResponse<Map<String, Object>> toggle(@PathVariable String documentId,
                                                   @Valid @RequestBody KnowledgeToggleRequest request) {
        return ApiResponse.ok(knowledgeService.toggle(documentId, request.enabled()));
    }

    @DeleteMapping("/{documentId}")
    public ApiResponse<Void> delete(@PathVariable String documentId) {
        knowledgeService.delete(documentId);
        return ApiResponse.ok(null);
    }

    @PostMapping("/rebuild")
    public ApiResponse<Map<String, Object>> rebuild() {
        return ApiResponse.ok(knowledgeService.rebuild());
    }
}
