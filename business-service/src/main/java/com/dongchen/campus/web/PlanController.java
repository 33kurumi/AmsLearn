package com.dongchen.campus.web;

import com.dongchen.campus.common.ApiResponse;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.service.PlanService;
import com.dongchen.campus.web.dto.PlanDayRequest;
import com.dongchen.campus.web.dto.PlanGenerateRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/plans")
public class PlanController {

    private final PlanService planService;

    public PlanController(PlanService planService) {
        this.planService = planService;
    }

    @PostMapping("/generate")
    public ApiResponse<Map<String, Object>> generate(@RequestBody(required = false) PlanGenerateRequest request) {
        String period = request == null ? null : request.period();
        Integer days = request == null ? null : request.days();
        java.util.List<String> focusKpIds = request == null ? null : request.focusKpIds();
        String goal = request == null ? null : request.goal();
        return ApiResponse.ok(planService.generate(period, days, focusKpIds, goal));
    }

    @GetMapping
    public ApiResponse<PageResult<Map<String, Object>>> list(@RequestParam(required = false) Integer page,
                                                             @RequestParam(required = false) Integer size) {
        return ApiResponse.ok(planService.list(page, size));
    }

    @GetMapping("/{id}")
    public ApiResponse<Map<String, Object>> detail(@PathVariable Long id) {
        return ApiResponse.ok(planService.detail(id));
    }

    @PatchMapping("/{id}/days/{dayIndex}")
    public ApiResponse<Map<String, Object>> toggleDay(@PathVariable Long id, @PathVariable Integer dayIndex,
                                                      @Valid @RequestBody PlanDayRequest request) {
        return ApiResponse.ok(planService.toggleDay(id, dayIndex, request.done()));
    }
}
