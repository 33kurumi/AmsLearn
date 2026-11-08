package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.domain.ClassTeacherConfig;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.KnowledgePoint;
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

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * S14 ~ S17 学习计划：生成、列表、详情、每日完成勾选。
 */
@Service
public class PlanService {

    private final AuthService authService;
    private final ConfigService configService;
    private final MasteryService masteryService;
    private final ReportRepository reportRepository;
    private final InteractionRecordRepository interactionRepository;
    private final AiServiceClient aiServiceClient;
    private final JsonHelper jsonHelper;
    private final ReportMapper reportMapper;

    public PlanService(AuthService authService, ConfigService configService,
                       MasteryService masteryService, ReportRepository reportRepository,
                       InteractionRecordRepository interactionRepository,
                       AiServiceClient aiServiceClient, JsonHelper jsonHelper,
                       ReportMapper reportMapper) {
        this.authService = authService;
        this.configService = configService;
        this.masteryService = masteryService;
        this.reportRepository = reportRepository;
        this.interactionRepository = interactionRepository;
        this.aiServiceClient = aiServiceClient;
        this.jsonHelper = jsonHelper;
        this.reportMapper = reportMapper;
    }

    @Transactional
    public Map<String, Object> generate(String period, Integer days, List<String> focusKpIds, String goal) {
        String planPeriod = normalizePeriod(period);
        int dayCount = days == null ? (("MONTH".equals(planPeriod)) ? 14 : 7) : days;
        if (dayCount < 1 || dayCount > 30) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "计划天数应在 1~30 天之间");
        }
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
        String planGoal = goal == null || goal.isBlank() ? "系统根据薄弱知识点自动生成学习计划" : goal.trim();

        JsonNode node = aiServiceClient.plan(Maps.of(
                "period", planPeriod,
                "days", dayCount,
                "focusKpIds", targetKpIds,
                "goal", planGoal,
                "mastery", masteryService.weakest(user.getId(), 20),
                "classId", user.getClassId(),
                "teacherConfig", configService.aiTeacherConfig(config)));
        List<Map<String, Object>> rawDays = jsonHelper.toMapList(node.get("days"));
        if (rawDays.isEmpty()) {
            throw new BusinessException(ErrorCode.AI_UNAVAILABLE, "智能服务未能生成学习计划，请稍后重试", 503);
        }
        String summary = jsonHelper.nodeText(node, "summary", "围绕薄弱知识点逐日突破。");
        LocalDate startDate = LocalDate.now().plusDays(1);
        List<Map<String, Object>> daysList = new ArrayList<>();
        int index = 0;
        for (Map<String, Object> rawDay : rawDays) {
            index++;
            Map<String, Object> day = new LinkedHashMap<>();
            day.put("dayIndex", rawDay.get("dayIndex") == null ? index : rawDay.get("dayIndex"));
            day.put("date", rawDay.get("date") == null ? startDate.plusDays(index - 1L).toString() : rawDay.get("date"));
            day.put("kpId", rawDay.get("kpId"));
            day.put("kpName", rawDay.get("kpName"));
            day.put("goal", rawDay.get("goal"));
            Map<String, Object> study = jsonHelper.toMap(rawDay.get("study"));
            if (study.isEmpty()) {
                study = Maps.of("summary", "", "points", List.of(), "example", "");
            }
            day.put("study", study);
            Map<String, Object> practice = jsonHelper.toMap(rawDay.get("practice"));
            if (practice.isEmpty()) {
                practice = Maps.of("questions", rawDay.get("practiceQuestions") == null ? List.of() : rawDay.get("practiceQuestions"));
            }
            day.put("practice", practice);
            Map<String, Object> review = jsonHelper.toMap(rawDay.get("review"));
            if (review.isEmpty()) {
                review = Maps.of("summary", "", "checklist", List.of());
            }
            day.put("review", review);
            day.put("done", Boolean.TRUE.equals(rawDay.get("done")));
            day.put("completedAt", rawDay.get("completedAt"));
            daysList.add(day);
        }

        Report report = new Report();
        report.setStudentId(user.getId());
        report.setClassId(user.getClassId());
        report.setType(ReportType.PLAN);
        report.setTitle(daysList.size() + "天高数强化计划");
        report.setSummary(summary);
        report.setStatus(ReportStatus.COMPLETED);
        report.setContent(jsonHelper.write(Maps.of(
                "period", planPeriod,
                "daysCount", daysList.size(),
                "startDate", startDate.toString(),
                "summary", summary,
                "days", daysList)));
        report.setCreatedAt(LocalDateTime.now());
        report.setUpdatedAt(LocalDateTime.now());
        reportRepository.save(report);

        InteractionRecord record = new InteractionRecord();
        record.setStudentId(user.getId());
        record.setClassId(user.getClassId());
        record.setType(RecordType.PLAN);
        record.setIntent("plan");
        record.setUserMessage("生成学习计划：" + planGoal);
        record.setAiResponse(summary);
        record.setSources("[]");
        record.setKpIds("[]");
        record.setKpNames("[]");
        record.setBlocked(false);
        record.setCreatedAt(LocalDateTime.now());
        interactionRepository.save(record);

        return reportMapper.planVo(report);
    }

    public PageResult<Map<String, Object>> list(Integer page, Integer size) {
        UserInfo user = authService.currentUser();
        List<Map<String, Object>> items = new ArrayList<>();
        for (Report report : reportRepository.findByStudentIdAndTypeOrderByCreatedAtDesc(user.getId(), ReportType.PLAN)) {
            items.add(reportMapper.planBrief(report));
        }
        return PageResult.of(items, page, size);
    }

    public Map<String, Object> detail(Long id) {
        UserInfo user = authService.currentUser();
        Report report = loadPlan(id, user.getId());
        return reportMapper.planVo(report);
    }

    @Transactional
    public Map<String, Object> toggleDay(Long id, Integer dayIndex, Boolean done) {
        if (dayIndex == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "dayIndex 不能为空");
        }
        if (done == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "done 不能为空");
        }
        UserInfo user = authService.currentUser();
        Report report = loadPlan(id, user.getId());
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        List<Map<String, Object>> days = new ArrayList<>();
        for (Object item : jsonHelper.toList(content.get("days"))) {
            days.add(jsonHelper.toMap(item));
        }
        boolean found = false;
        for (Map<String, Object> day : days) {
            Object value = day.get("dayIndex");
            int index = value instanceof Number number ? number.intValue() : -1;
            if (index == dayIndex) {
                day.put("done", done);
                day.put("completedAt", done ? LocalDateTime.now().toString() : null);
                found = true;
            }
        }
        if (!found) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "计划中不存在该天");
        }
        content.put("days", days);
        report.setContent(jsonHelper.write(content));
        report.setUpdatedAt(LocalDateTime.now());
        reportRepository.save(report);
        return reportMapper.planVo(report);
    }

    private Report loadPlan(Long id, Long studentId) {
        Report report = reportRepository.findByIdAndStudentId(id, studentId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "学习计划不存在"));
        if (report.getType() != ReportType.PLAN) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "学习计划不存在");
        }
        return report;
    }

    private String normalizePeriod(String period) {
        if (period == null || period.isBlank()) {
            return "WEEK";
        }
        String value = period.trim().toUpperCase();
        if (!"WEEK".equals(value) && !"MONTH".equals(value)) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "计划周期仅支持 WEEK 或 MONTH");
        }
        return value;
    }
}
