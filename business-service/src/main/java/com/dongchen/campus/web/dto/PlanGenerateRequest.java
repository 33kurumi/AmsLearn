package com.dongchen.campus.web.dto;

import java.util.List;

public record PlanGenerateRequest(String period, Integer days, List<String> focusKpIds, String goal) {
}
