package com.dongchen.campus.web.dto;

import java.util.List;
import java.util.Map;

public record ConfigSaveRequest(String answerMode, Integer maxDifficulty,
                                Map<String, Object> knowledgeScope, String boundaryRules,
                                Map<String, Object> kbAccess, List<String> disabledTopics) {
}
