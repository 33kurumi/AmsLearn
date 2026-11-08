package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.service.StudentService;
import com.dongchen.campus.web.dto.WrongQuestionRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/student")
public class StudentController {

    private final StudentService studentService;

    public StudentController(StudentService studentService) {
        this.studentService = studentService;
    }

    @GetMapping("/dashboard")
    public ApiResponse<Map<String, Object>> dashboard() {
        return ApiResponse.ok(studentService.dashboard());
    }

    @GetMapping("/knowledge-points")
    public ApiResponse<List<Map<String, Object>>> knowledgePoints() {
        return ApiResponse.ok(studentService.knowledgePoints());
    }

    @GetMapping("/records")
    public ApiResponse<PageResult<Map<String, Object>>> records(
            @RequestParam(required = false) String type,
            @RequestParam(required = false) String kpId,
            @RequestParam(required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(studentService.records(type, kpId, from, to, page, size));
    }

    @GetMapping("/records/{id}")
    public ApiResponse<Map<String, Object>> recordDetail(@PathVariable Long id) {
        return ApiResponse.ok(studentService.recordDetail(id));
    }

    @GetMapping("/reports")
    public ApiResponse<PageResult<Map<String, Object>>> reports(
            @RequestParam(required = false) String type,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(studentService.reports(type, page, size));
    }

    @GetMapping("/reports/{id}")
    public ApiResponse<Map<String, Object>> reportDetail(@PathVariable Long id) {
        return ApiResponse.ok(studentService.reportDetail(id));
    }

    @GetMapping("/wrong-questions")
    public ApiResponse<Map<String, Object>> wrongQuestions(
            @RequestParam(required = false) String kpId,
            @RequestParam(required = false) String errorType,
            @RequestParam(required = false) Boolean reviewed,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(studentService.wrongQuestions(kpId, errorType, reviewed, page, size));
    }

    @PatchMapping("/wrong-questions/{id}")
    public ApiResponse<Map<String, Object>> markWrongQuestion(@PathVariable Long id,
                                                              @Valid @RequestBody WrongQuestionRequest request) {
        return ApiResponse.ok(studentService.markWrongQuestion(id, request.reviewed()));
    }
}
