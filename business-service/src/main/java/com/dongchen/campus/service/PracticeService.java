package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.ClassTeacherConfig;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.PracticeLayer;
import com.dongchen.campus.domain.RecordType;
import com.dongchen.campus.domain.Report;
import com.dongchen.campus.domain.ReportStatus;
import com.dongchen.campus.domain.ReportType;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.InteractionRecordRepository;
import com.dongchen.campus.repository.ReportRepository;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * S12 / S13 分层练习与思路提示。
 */
@Service
public class PracticeService {

    private final AuthService authService;
    private final ConfigService configService;
    private final MasteryService masteryService;
    private final ReportRepository reportRepository;
    private final InteractionRecordRepository interactionRepository;
    private final AiServiceClient aiServiceClient;
    private final JsonHelper jsonHelper;

    public PracticeService(AuthService authService, ConfigService configService,
                           MasteryService masteryService, ReportRepository reportRepository,
                           InteractionRecordRepository interactionRepository,
                           AiServiceClient aiServiceClient, JsonHelper jsonHelper) {
        this.authService = authService;
        this.configService = configService;
        this.masteryService = masteryService;
        this.reportRepository = reportRepository;
        this.interactionRepository = interactionRepository;
        this.aiServiceClient = aiServiceClient;
        this.jsonHelper = jsonHelper;
    }

    @Transactional
    public Map<String, Object> generate(String layer, Integer count, List<String> kpIds) {
        String practiceLayer = normalizeLayer(layer);
        int questionCount = count == null ? 5 : Math.min(Math.max(count, 1), 20);
        UserInfo user = authService.currentUser();
        ClassTeacherConfig config = configService.getOrCreate(user.getClassId());
        Map<String, KnowledgePoint> kpMap = masteryService.kpMap();

        List<String> targetKpIds = new ArrayList<>();
        if (kpIds != null) {
            for (String kpId : kpIds) {
                if (kpId != null && kpMap.containsKey(kpId)) {
                    targetKpIds.add(kpId);
                }
            }
        }
        if (targetKpIds.isEmpty()) {
            targetKpIds = configService.effectiveKpIds(config);
        }

        JsonNode node = aiServiceClient.practiceQuestions(Maps.of(
                "layer", practiceLayer,
                "count", questionCount,
                "difficultyMax", config.getMaxDifficulty(),
                "kpIds", targetKpIds,
                "classId", user.getClassId(),
                "teacherConfig", configService.aiTeacherConfig(config)));
        List<Map<String, Object>> questions = publicQuestions(jsonHelper.toMapList(node.get("questions")));
        if (questions.isEmpty()) {
            throw new BusinessException(ErrorCode.AI_UNAVAILABLE, "智能服务未能生成练习题目，请稍后重试", 503);
        }
        String guidance = jsonHelper.nodeText(node, "guidance", "");

        Set<String> kpNames = new LinkedHashSet<>();
        for (Map<String, Object> question : questions) {
            Object name = question.get("kpName");
            if (name != null) {
                kpNames.add(String.valueOf(name));
            }
        }
        Map<String, Object> content = new LinkedHashMap<>();
        content.put("batchId", "");
        content.put("layer", practiceLayer);
        content.put("kpIds", targetKpIds);
        content.put("kpNames", new ArrayList<>(kpNames));
        content.put("questions", questions);
        content.put("guidance", guidance);

        Report report = new Report();
        report.setStudentId(user.getId());
        report.setClassId(user.getClassId());
        report.setType(ReportType.PRACTICE);
        report.setTitle(questionCount + " 题高数" + practiceLayer + "级练习");
        report.setSummary("本批次共 " + questions.size() + " 题，覆盖 " + kpNames.size() + " 个知识点。");
        report.setStatus(ReportStatus.COMPLETED);
        report.setCreatedAt(LocalDateTime.now());
        report.setUpdatedAt(LocalDateTime.now());
        report.setContent(jsonHelper.write(content));
        reportRepository.save(report);

        String batchId = "p-" + report.getId();
        content.put("batchId", batchId);
        report.setContent(jsonHelper.write(content));
        reportRepository.save(report);

        InteractionRecord record = new InteractionRecord();
        record.setStudentId(user.getId());
        record.setClassId(user.getClassId());
        record.setType(RecordType.PRACTICE);
        record.setIntent("practice");
        record.setUserMessage("生成 " + practiceLayer + " 级练习 " + questions.size() + " 题");
        record.setAiResponse(guidance);
        record.setSources("[]");
        record.setKpIds(jsonHelper.write(targetKpIds));
        record.setKpNames(jsonHelper.write(new ArrayList<>(kpNames)));
        record.setBlocked(false);
        record.setCreatedAt(LocalDateTime.now());
        interactionRepository.save(record);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("batchId", batchId);
        result.put("layer", practiceLayer);
        result.put("kpNames", new ArrayList<>(kpNames));
        result.put("createdAt", report.getCreatedAt());
        result.put("questions", questions);
        result.put("guidance", guidance);
        return result;
    }

    public Map<String, Object> hint(String batchId, String questionId, String studentAnswer) {
        if (batchId == null || batchId.isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "batchId 不能为空");
        }
        UserInfo user = authService.currentUser();
        Report report = null;
        for (Report candidate : reportRepository.findByStudentIdAndTypeOrderByCreatedAtDesc(user.getId(), ReportType.PRACTICE)) {
            Map<String, Object> content = jsonHelper.readMap(candidate.getContent());
            if (batchId.equals(String.valueOf(content.get("batchId")))) {
                report = candidate;
                break;
            }
        }
        if (report == null) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "练习批次不存在");
        }
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        List<Map<String, Object>> questions = new ArrayList<>();
        for (Object item : jsonHelper.toList(content.get("questions"))) {
            questions.add(jsonHelper.toMap(item));
        }
        Map<String, Object> target = null;
        for (Map<String, Object> question : questions) {
            if (questionId != null && questionId.equals(String.valueOf(question.get("questionId")))) {
                target = question;
                break;
            }
        }
        if (target == null) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "练习题目不存在");
        }
        ClassTeacherConfig config = configService.getOrCreate(user.getClassId());
        Map<String, Object> question = Maps.of(
                "questionId", target.get("questionId"),
                "stem", target.get("stem"),
                "kpId", target.get("kpId"),
                "kpName", target.get("kpName"),
                "layer", content.get("layer"));
        JsonNode node = aiServiceClient.practiceHint(Maps.of(
                "question", question,
                "studentAnswer", studentAnswer,
                "teacherConfig", configService.aiTeacherConfig(config)));
        List<Object> sources = jsonHelper.toList(jsonHelper.mapper().convertValue(node.path("sources"), Object.class));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("hint", jsonHelper.nodeText(node, "hint", ""));
        result.put("sources", sources);
        result.put("strategy", jsonHelper.nodeText(node, "strategy", ""));
        return result;
    }

    /**
     * 下发学生端的题目不得包含 answerKey / analysis（契约 3.6 Question），只保留契约字段。
     */
    private List<Map<String, Object>> publicQuestions(List<Map<String, Object>> questions) {
        List<Map<String, Object>> list = new ArrayList<>();
        for (Map<String, Object> question : questions) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("questionId", question.get("questionId"));
            item.put("index", question.get("index"));
            item.put("kpId", question.get("kpId"));
            item.put("kpName", question.get("kpName"));
            item.put("difficulty", question.get("difficulty"));
            item.put("type", question.get("type"));
            item.put("stem", question.get("stem"));
            item.put("options", question.get("options") == null ? List.of() : question.get("options"));
            item.put("hint", question.get("hint"));
            list.add(item);
        }
        return list;
    }

    private String normalizeLayer(String layer) {
        if (layer == null || layer.isBlank()) {
            return PracticeLayer.B.name();
        }
        try {
            return PracticeLayer.valueOf(layer.trim().toUpperCase()).name();
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "练习层次仅支持 A/B/C");
        }
    }
}
