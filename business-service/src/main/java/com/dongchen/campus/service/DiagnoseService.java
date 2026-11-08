package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.ClassTeacherConfig;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.RecordType;
import com.dongchen.campus.domain.Report;
import com.dongchen.campus.domain.ReportStatus;
import com.dongchen.campus.domain.ReportType;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.domain.WrongQuestion;
import com.dongchen.campus.repository.InteractionRecordRepository;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.dongchen.campus.repository.ReportRepository;
import com.dongchen.campus.repository.WrongQuestionRepository;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * S10 / S11 诊断：出题、批改、掌握度更新、错题沉淀、生成诊断报告。
 */
@Service
public class DiagnoseService {

    private static final int QUICK_COUNT = 5;
    private static final int FULL_COUNT = 15;

    private final AuthService authService;
    private final ConfigService configService;
    private final MasteryService masteryService;
    private final ReportRepository reportRepository;
    private final WrongQuestionRepository wrongQuestionRepository;
    private final InteractionRecordRepository interactionRepository;
    private final KnowledgePointRepository knowledgePointRepository;
    private final AiServiceClient aiServiceClient;
    private final JsonHelper jsonHelper;
    private final ReportMapper reportMapper;

    public DiagnoseService(AuthService authService, ConfigService configService,
                           MasteryService masteryService, ReportRepository reportRepository,
                           WrongQuestionRepository wrongQuestionRepository,
                           InteractionRecordRepository interactionRepository,
                           KnowledgePointRepository knowledgePointRepository,
                           AiServiceClient aiServiceClient, JsonHelper jsonHelper,
                           ReportMapper reportMapper) {
        this.authService = authService;
        this.configService = configService;
        this.masteryService = masteryService;
        this.reportRepository = reportRepository;
        this.wrongQuestionRepository = wrongQuestionRepository;
        this.interactionRepository = interactionRepository;
        this.knowledgePointRepository = knowledgePointRepository;
        this.aiServiceClient = aiServiceClient;
        this.jsonHelper = jsonHelper;
        this.reportMapper = reportMapper;
    }

    @Transactional
    public Map<String, Object> start(String mode, List<String> focusKpIds) {
        String diagnoseMode = normalizeMode(mode);
        UserInfo user = authService.currentUser();
        ClassTeacherConfig config = configService.getOrCreate(user.getClassId());
        Map<String, KnowledgePoint> kpMap = masteryService.kpMap();

        List<String> targetKpIds = new ArrayList<>();
        if (focusKpIds != null) {
            for (String kpId : focusKpIds) {
                if (kpId != null && kpMap.containsKey(kpId)) {
                    targetKpIds.add(kpId);
                }
            }
        }
        if (targetKpIds.isEmpty()) {
            targetKpIds = configService.effectiveKpIds(config);
        }
        int count = "FULL".equals(diagnoseMode) ? FULL_COUNT : QUICK_COUNT;

        Map<String, Object> body = Maps.of(
                "mode", diagnoseMode,
                "count", count,
                "difficultyMax", config.getMaxDifficulty(),
                "kpIds", targetKpIds,
                "mastery", masteryService.weakest(user.getId(), 20),
                "classId", user.getClassId(),
                "teacherConfig", configService.aiTeacherConfig(config));
        JsonNode node = aiServiceClient.diagnoseQuestions(body);
        List<Map<String, Object>> questions = jsonHelper.toMapList(node.get("questions"));
        if (questions.isEmpty()) {
            throw new BusinessException(ErrorCode.AI_UNAVAILABLE, "智能服务未能生成诊断题目，请稍后重试", 503);
        }

        Report report = new Report();
        report.setStudentId(user.getId());
        report.setClassId(user.getClassId());
        report.setType(ReportType.DIAGNOSIS);
        report.setTitle("FULL".equals(diagnoseMode) ? "全面诊断报告" : "快速诊断报告");
        report.setSummary("共 " + questions.size() + " 题，待提交答案后生成诊断报告");
        report.setStatus(ReportStatus.DRAFT);
        report.setContent(jsonHelper.write(Maps.of(
                "mode", diagnoseMode,
                "total", questions.size(),
                "questions", questions)));
        report.setCreatedAt(LocalDateTime.now());
        report.setUpdatedAt(LocalDateTime.now());
        reportRepository.save(report);

        InteractionRecord record = new InteractionRecord();
        record.setStudentId(user.getId());
        record.setClassId(user.getClassId());
        record.setType(RecordType.DIAGNOSIS);
        record.setIntent("diagnose");
        record.setUserMessage("开始" + ("FULL".equals(diagnoseMode) ? "全面" : "快速") + "诊断");
        record.setAiResponse("");
        record.setSources("[]");
        record.setKpIds(jsonHelper.write(targetKpIds));
        record.setKpNames(jsonHelper.write(kpNames(targetKpIds, kpMap)));
        record.setBlocked(false);
        record.setCreatedAt(LocalDateTime.now());
        interactionRepository.save(record);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sessionId", report.getId());
        result.put("reportId", report.getId());
        result.put("mode", diagnoseMode);
        result.put("total", questions.size());
        result.put("startedAt", report.getCreatedAt());
        result.put("questions", stripQuestions(questions));
        return result;
    }

    @Transactional
    public Map<String, Object> submit(Long sessionId, List<Map<String, Object>> answers) {
        UserInfo user = authService.currentUser();
        Report report = reportRepository.findByIdAndStudentId(sessionId, user.getId())
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "诊断会话不存在"));
        if (report.getType() != ReportType.DIAGNOSIS) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "该会话不是诊断会话");
        }
        if (report.getStatus() == ReportStatus.COMPLETED) {
            throw new BusinessException(ErrorCode.CONFLICT, "该诊断已提交，请重新开始诊断");
        }
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        List<Map<String, Object>> questions = new ArrayList<>();
        for (Object item : jsonHelper.toList(content.get("questions"))) {
            questions.add(jsonHelper.toMap(item));
        }
        List<Map<String, Object>> answerList = answers == null ? List.of() : answers;

        JsonNode node = aiServiceClient.grade(Maps.of("questions", questions, "answers", answerList));
        List<Map<String, Object>> results = jsonHelper.toMapList(node.get("results"));
        int total = content.get("total") == null ? questions.size() : toInt(content.get("total"), questions.size());
        int correctCount = 0;
        for (Map<String, Object> resultItem : results) {
            if (Boolean.TRUE.equals(resultItem.get("correct"))) {
                correctCount++;
            }
        }
        double scoreValue = node.path("score").asDouble(results.isEmpty() ? 0 : Math.round(100.0 * correctCount / results.size()));
        int score = (int) Math.round(scoreValue);
        String level = jsonHelper.nodeText(node, "level", levelOf(score));
        List<Object> errorSummary = jsonHelper.toList(jsonHelper.mapper().convertValue(node.path("errorSummary"), Object.class));
        List<Object> advice = jsonHelper.toList(jsonHelper.mapper().convertValue(node.path("advice"), Object.class));

        Map<String, Map<String, Object>> questionById = new LinkedHashMap<>();
        for (Map<String, Object> question : questions) {
            Object questionId = question.get("questionId");
            if (questionId != null) {
                questionById.put(String.valueOf(questionId), question);
            }
        }
        Map<String, String> answerByQuestion = new LinkedHashMap<>();
        for (Map<String, Object> answer : answerList) {
            if (answer.get("questionId") != null) {
                answerByQuestion.put(String.valueOf(answer.get("questionId")),
                        answer.get("answer") == null ? "" : String.valueOf(answer.get("answer")));
            }
        }

        List<Map<String, Object>> masteryChanges = new ArrayList<>();
        for (Map<String, Object> resultItem : results) {
            Map<String, Object> question = questionById.get(String.valueOf(resultItem.get("questionId")));
            String kpId = resultItem.get("kpId") == null
                    ? (question == null ? null : str(question.get("kpId")))
                    : str(resultItem.get("kpId"));
            if (kpId == null || kpId.isBlank()) {
                continue;
            }
            boolean correct = Boolean.TRUE.equals(resultItem.get("correct"));
            masteryChanges.add(masteryService.applyAnswer(user.getId(), kpId, correct));
            if (!correct) {
                WrongQuestion wrong = new WrongQuestion();
                wrong.setStudentId(user.getId());
                wrong.setClassId(user.getClassId());
                wrong.setKpId(kpId);
                wrong.setKpName(question == null ? str(resultItem.get("kpName")) : str(question.get("kpName")));
                wrong.setQuestionText(question == null ? str(resultItem.get("stem")) : str(question.get("stem")));
                wrong.setQuestionType(question == null ? str(resultItem.get("type")) : str(question.get("type")));
                wrong.setDifficulty(question == null ? toInt(resultItem.get("difficulty"), 0) : toInt(question.get("difficulty"), 0));
                wrong.setStudentAnswer(resultItem.get("studentAnswer") == null
                        ? answerByQuestion.get(str(resultItem.get("questionId")))
                        : str(resultItem.get("studentAnswer")));
                wrong.setCorrectAnswer(resultItem.get("correctAnswer") == null
                        ? (question == null ? null : str(question.get("answerKey")))
                        : str(resultItem.get("correctAnswer")));
                wrong.setErrorType(str(resultItem.get("errorType")));
                wrong.setAnalysis(str(resultItem.get("analysis")));
                wrong.setSourceType("DIAGNOSIS");
                wrong.setReviewed(false);
                wrong.setCreatedAt(LocalDateTime.now());
                wrongQuestionRepository.save(wrong);
            }
        }

        List<Map<String, Object>> weakTop5 = masteryService.weakTop5WithAccuracy(user.getId());
        Map<String, Object> newContent = new LinkedHashMap<>();
        newContent.put("mode", content.get("mode"));
        newContent.put("total", total);
        newContent.put("correctCount", correctCount);
        newContent.put("score", score);
        newContent.put("level", level);
        newContent.put("weakTop5", weakTop5);
        newContent.put("errorSummary", errorSummary);
        newContent.put("advice", advice);
        report.setContent(jsonHelper.write(newContent));
        report.setStatus(ReportStatus.COMPLETED);
        report.setSummary("本次诊断共 " + total + " 题，答对 " + correctCount + " 题，得分 " + score + "（" + level + "）。");
        report.setUpdatedAt(LocalDateTime.now());
        reportRepository.save(report);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportId", report.getId());
        result.put("total", total);
        result.put("correctCount", correctCount);
        result.put("score", score);
        result.put("level", level);
        result.put("results", results);
        result.put("masteryChanges", masteryChanges);
        result.put("report", reportMapper.reportVo(report));
        return result;
    }

    private List<Map<String, Object>> stripQuestions(List<Map<String, Object>> questions) {
        List<Map<String, Object>> stripped = new ArrayList<>();
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
            stripped.add(item);
        }
        return stripped;
    }

    private List<String> kpNames(List<String> kpIds, Map<String, KnowledgePoint> kpMap) {
        List<String> names = new ArrayList<>();
        for (String kpId : kpIds) {
            KnowledgePoint point = kpMap.get(kpId);
            if (point != null) {
                names.add(point.getKpName());
            }
        }
        return names;
    }

    private String normalizeMode(String mode) {
        if (mode == null || mode.isBlank()) {
            return "QUICK";
        }
        String value = mode.trim().toUpperCase();
        if (!"QUICK".equals(value) && !"FULL".equals(value)) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "诊断模式仅支持 QUICK 或 FULL");
        }
        return value;
    }

    private static String str(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static int toInt(Object value, int fallback) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value == null) {
            return fallback;
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException ex) {
            return fallback;
        }
    }

    private static String levelOf(int score) {
        if (score >= 85) {
            return "优秀";
        }
        if (score >= 70) {
            return "良好";
        }
        if (score >= 55) {
            return "一般";
        }
        return "待提升";
    }
}
