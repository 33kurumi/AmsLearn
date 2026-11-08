package com.dongchen.campus.service;

import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.repository.KnowledgePointRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class MetaService {

    private static final List<String> ERROR_TYPES =
            List.of("概念混淆", "计算失误", "审题偏差", "方法不当");

    private final KnowledgePointRepository knowledgePointRepository;

    public MetaService(KnowledgePointRepository knowledgePointRepository) {
        this.knowledgePointRepository = knowledgePointRepository;
    }

    public List<Map<String, Object>> knowledgePoints() {
        List<Map<String, Object>> result = new ArrayList<>();
        for (KnowledgePoint point : knowledgePointRepository.findAllByOrderByOrderIndexAsc()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("kpId", point.getKpId());
            item.put("kpName", point.getKpName());
            item.put("chapter", point.getChapter());
            item.put("difficulty", point.getDifficulty());
            item.put("hours", point.getHours());
            item.put("objectives", point.getObjectives());
            item.put("keyPoints", point.getKeyPoints());
            result.add(item);
        }
        return result;
    }

    public Map<String, Object> dictionaries() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("answerModes", List.of(
                Maps.of("value", "GUIDED", "label", "引导式",
                        "desc", "先给思路与关键步骤，由学生自己完成计算"),
                Maps.of("value", "DIRECT", "label", "直接讲解",
                        "desc", "直接给出完整讲解与答案"),
                Maps.of("value", "MIXED", "label", "混合",
                        "desc", "按知识点难度与学生掌握度自动选择引导或讲解")));
        result.put("difficulties", List.of(
                Maps.of("value", 1, "label", "基础"),
                Maps.of("value", 2, "label", "常规"),
                Maps.of("value", 3, "label", "较难"),
                Maps.of("value", 4, "label", "拓展")));
        result.put("layers", List.of(
                Maps.of("value", "A", "label", "基础"),
                Maps.of("value", "B", "label", "提升"),
                Maps.of("value", "C", "label", "拓展")));
        result.put("errorTypes", ERROR_TYPES);
        result.put("periods", List.of(
                Maps.of("value", "7D", "label", "近7天"),
                Maps.of("value", "30D", "label", "近30天"),
                Maps.of("value", "TERM", "label", "本学期")));
        return result;
    }
}
