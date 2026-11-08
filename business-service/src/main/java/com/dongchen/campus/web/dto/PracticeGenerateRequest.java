package com.dongchen.campus.web.dto;

import java.util.List;

public record PracticeGenerateRequest(String layer, Integer count, List<String> kpIds) {
}
