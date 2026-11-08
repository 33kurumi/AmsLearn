package com.dongchen.campus.web.dto;

import java.util.List;

public record DiagnoseStartRequest(String mode, List<String> focusKpIds) {
}
