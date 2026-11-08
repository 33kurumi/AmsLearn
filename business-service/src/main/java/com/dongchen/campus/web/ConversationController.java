package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.service.ConversationService;
import com.dongchen.campus.web.dto.ConversationRequest;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * v1.2 答疑会话：本人会话 CRUD 与历史消息。
 */
@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    @PostMapping
    public ApiResponse<Map<String, Object>> create(@RequestBody(required = false) ConversationRequest request) {
        return ApiResponse.ok(conversationService.create(request == null ? null : request.title()));
    }

    @GetMapping
    public ApiResponse<PageResult<Map<String, Object>>> list(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(conversationService.list(page, size));
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@PathVariable Long id) {
        return ApiResponse.ok(conversationService.detail(id));
    }

    @PatchMapping("/{id}")
    public ApiResponse<Map<String, Object>> rename(@PathVariable Long id,
                                                   @RequestBody ConversationRequest request) {
        return ApiResponse.ok(conversationService.rename(id, request == null ? null : request.title()));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        conversationService.delete(id);
        return ApiResponse.ok(null);
    }
}
