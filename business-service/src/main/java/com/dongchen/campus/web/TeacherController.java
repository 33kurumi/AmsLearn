package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.service.TeacherService;
import com.dongchen.campus.web.dto.ConfigExtractRequest;
import com.dongchen.campus.web.dto.ConfigSaveRequest;
import com.dongchen.campus.web.dto.TeacherResetPasswordRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/teacher")
public class TeacherController {

    private final TeacherService teacherService;
    private final JsonHelper jsonHelper;

    public TeacherController(TeacherService teacherService, JsonHelper jsonHelper) {
        this.teacherService = teacherService;
        this.jsonHelper = jsonHelper;
    }

    @GetMapping("/dashboard")
    public ApiResponse<Map<String, Object>> dashboard() {
        return ApiResponse.ok(teacherService.dashboard());
    }

    @GetMapping("/config")
    public ApiResponse<Map<String, Object>> config() {
        return ApiResponse.ok(teacherService.config());
    }

    @PutMapping("/config")
    public ApiResponse<Map<String, Object>> saveConfig(@RequestBody ConfigSaveRequest request) {
        Map<String, Object> body = Maps.of(
                "answerMode", request.answerMode(),
                "maxDifficulty", request.maxDifficulty(),
                "knowledgeScope", request.knowledgeScope(),
                "boundaryRules", request.boundaryRules(),
                "kbAccess", request.kbAccess(),
                "disabledTopics", request.disabledTopics());
        return ApiResponse.ok(teacherService.saveConfig(body));
    }

    @GetMapping("/config/logs")
    public ApiResponse<PageResult<Map<String, Object>>> configLogs(@RequestParam(required = false) Integer page,
                                                                  @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(teacherService.configLogs(page, size));
    }

    @PostMapping("/config/extract")
    public ApiResponse<Map<String, Object>> extractConfig(@Valid @RequestBody ConfigExtractRequest request) {
        return ApiResponse.ok(teacherService.extractConfig(request.text()));
    }

    @GetMapping("/analysis")
    public ApiResponse<Map<String, Object>> analysis(@RequestParam(required = false, defaultValue = "30D") String period) {
        return ApiResponse.ok(teacherService.analysis(period));
    }

    @GetMapping("/students")
    public ApiResponse<List<Map<String, Object>>> students() {
        return ApiResponse.ok(teacherService.students());
    }

    /** v1.4 教师重置本班学生密码。 */
    @PutMapping("/students/{studentId}/password")
    public ApiResponse<Void> resetStudentPassword(@PathVariable Long studentId,
                                                  @Valid @RequestBody TeacherResetPasswordRequest request) {
        teacherService.resetStudentPassword(studentId, request.newPassword());
        return ApiResponse.ok(null);
    }

    @GetMapping("/students/{studentId}/records")
    public ApiResponse<PageResult<Map<String, Object>>> studentRecords(
            @PathVariable Long studentId,
            @RequestParam(required = false) String type,
            @RequestParam(required = false) String kpId,
            @RequestParam(required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(teacherService.studentRecords(studentId, type, kpId, from, to, page, size));
    }
}
