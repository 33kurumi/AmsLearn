package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.service.ChatService;
import com.dongchen.campus.web.dto.ChatRequest;
import com.dongchen.campus.web.dto.GateCheckRequest;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @PostMapping("/chat")
    public ApiResponse<Map<String, Object>> chat(@Valid @RequestBody ChatRequest request) {
        return ApiResponse.ok(chatService.chat(request.message(), request.conversationId()));
    }

    /** v1.3 图片答疑：multipart 字段 file，识别为文字后由前端回填输入框。 */
    @PostMapping(value = "/student/chat/vision", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<Map<String, Object>> chatVision(@RequestParam("file") MultipartFile file) {
        return ApiResponse.ok(chatService.visionExtract(file));
    }

    /** v1.3 前置自测提交：通过后 AI 返回循序渐进教学。 */
    @PostMapping("/student/gate/check")
    public ApiResponse<Map<String, Object>> gateCheck(@Valid @RequestBody GateCheckRequest request) {
        List<Map<String, Object>> answers = new ArrayList<>();
        for (GateCheckRequest.Answer answer : request.answers()) {
            answers.add(Maps.of("questionId", answer.questionId(), "choice", answer.choice()));
        }
        return ApiResponse.ok(chatService.gateCheck(request.gateId(), request.conversationId(), answers));
    }
}
