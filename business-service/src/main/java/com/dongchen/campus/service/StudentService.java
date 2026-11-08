package com.dongchen.campus.service;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.RecordType;
import com.dongchen.campus.domain.Report;
import com.dongchen.campus.domain.ReportType;
import com.dongchen.campus.domain.StudentKpMastery;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.domain.WrongQuestion;
import com.dongchen.campus.repository.InteractionRecordRepository;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.dongchen.campus.repository.ReportRepository;
import com.dongchen.campus.repository.StudentKpMasteryRepository;
import com.dongchen.campus.repository.WrongQuestionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 学生端业务：首页、知识点掌握度、学习记录、报告、错题。
 */
@Service
public class StudentService {

    private static final double WEAK_THRESHOLD = 0.3;
    private static final double GOOD_THRESHOLD = 0.7;

    private final AuthService authService;
    private final UserMapper userMapper;
    private final KnowledgePointRepository knowledgePointRepository;
    private final StudentKpMasteryRepository masteryRepository;
    private final InteractionRecordRepository interactionRepository;
    private final WrongQuestionRepository wrongQuestionRepository;
    private final ReportRepository reportRepository;
    private final JsonHelper jsonHelper;
    private final ReportMapper reportMapper;

    public StudentService(AuthService authService, UserMapper userMapper,
                          KnowledgePointRepository knowledgePointRepository,
                          StudentKpMasteryRepository masteryRepository,
                          InteractionRecordRepository interactionRepository,
                          WrongQuestionRepository wrongQuestionRepository,
                          ReportRepository reportRepository, JsonHelper jsonHelper,
                          ReportMapper reportMapper) {
        this.authService = authService;
        this.userMapper = userMapper;
        this.knowledgePointRepository = knowledgePointRepository;
        this.masteryRepository = masteryRepository;
        this.interactionRepository = interactionRepository;
        this.wrongQuestionRepository = wrongQuestionRepository;
        this.reportRepository = reportRepository;
        this.jsonHelper = jsonHelper;
        this.reportMapper = reportMapper;
    }

    // ---------- S1 首页 ----------

    public Map<String, Object> dashboard() {
        UserInfo user = authService.currentUser();
        List<KnowledgePoint> points = knowledgePointRepository.findAllByOrderByOrderIndexAsc();
        Map<String, StudentKpMastery> masteryMap = masteryMap(user.getId());

        double sum = 0;
        int weakCount = 0;
        int[] bins = new int[5];
        List<Map<String, Object>> ranked = new ArrayList<>();
        for (KnowledgePoint point : points) {
            StudentKpMastery row = masteryMap.get(point.getKpId());
            double mastery = row == null ? 0.0 : clamp(row.getMastery());
            sum += mastery;
            if (mastery < WEAK_THRESHOLD) {
                weakCount++;
            }
            int bin = Math.min(4, Math.max(0, (int) Math.floor(mastery * 5)));
            bins[bin]++;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("kpId", point.getKpId());
            item.put("kpName", point.getKpName());
            item.put("chapter", point.getChapter());
            item.put("mastery", ReportMapper.round2(mastery));
            ranked.add(item);
        }
        double avg = points.isEmpty() ? 0.0 : sum / points.size();
        ranked.sort(Comparator.comparingDouble(o -> (Double) o.get("mastery")));
        List<Map<String, Object>> weakTop5 = ranked.subList(0, Math.min(5, ranked.size()));

        String[] ranges = {"0-20%", "20-40%", "40-60%", "60-80%", "80-100%"};
        List<Map<String, Object>> distribution = new ArrayList<>();
        for (int i = 0; i < ranges.length; i++) {
            distribution.add(Maps.of("range", ranges[i], "count", bins[i]));
        }

        LocalDateTime todayStart = LocalDate.now().atStartOfDay();
        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("interactionCount", interactionRepository.countByStudentId(user.getId()));
        stats.put("diagnosisCount", interactionRepository.countByStudentIdAndType(user.getId(), RecordType.DIAGNOSIS));
        stats.put("practiceCount", interactionRepository.countByStudentIdAndType(user.getId(), RecordType.PRACTICE));
        stats.put("planCount", interactionRepository.countByStudentIdAndType(user.getId(), RecordType.PLAN));
        stats.put("wrongCount", wrongQuestionRepository.countByStudentId(user.getId()));
        stats.put("unreviewedWrongCount", wrongQuestionRepository.countByStudentIdAndReviewedFalse(user.getId()));
        stats.put("todayInteractionCount",
                interactionRepository.countByStudentIdAndCreatedAtGreaterThanEqual(user.getId(), todayStart));

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("user", userMapper.toVo(user));
        result.put("classInfo", userMapper.classInfoVo(user.getClassId()));
        result.put("mastery", Maps.of(
                "avg", ReportMapper.round2(avg),
                "weakCount", weakCount,
                "totalKp", points.size(),
                "distribution", distribution));
        result.put("weakTop5", weakTop5);
        result.put("stats", stats);
        result.put("currentPlan", currentPlan(user.getId()));
        result.put("recentReports", recentReports(user.getId()));
        return result;
    }

    private Map<String, Object> currentPlan(Long studentId) {
        Optional<Report> plan = reportRepository.findFirstByStudentIdAndTypeOrderByCreatedAtDesc(studentId, ReportType.PLAN);
        if (plan.isEmpty()) {
            return null;
        }
        Report report = plan.get();
        List<Map<String, Object>> days = reportMapper.planDays(report);
        int doneDays = 0;
        for (Map<String, Object> day : days) {
            if (Boolean.TRUE.equals(day.get("done"))) {
                doneDays++;
            }
        }
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        return Maps.of(
                "id", report.getId(),
                "title", report.getTitle(),
                "period", content.get("period"),
                "progress", days.isEmpty() ? 0.0 : ReportMapper.round2(doneDays / (double) days.size()),
                "daysCount", days.size(),
                "doneDays", doneDays);
    }

    private List<Map<String, Object>> recentReports(Long studentId) {
        List<Report> reports = reportRepository.findByStudentIdOrderByCreatedAtDesc(studentId);
        List<Map<String, Object>> result = new ArrayList<>();
        int limit = Math.min(5, reports.size());
        for (int i = 0; i < limit; i++) {
            result.add(reportMapper.reportBrief(reports.get(i)));
        }
        return result;
    }

    // ---------- S2 知识点与掌握度 ----------

    public List<Map<String, Object>> knowledgePoints() {
        UserInfo user = authService.currentUser();
        Map<String, StudentKpMastery> masteryMap = masteryMap(user.getId());
        List<Map<String, Object>> result = new ArrayList<>();
        for (KnowledgePoint point : knowledgePointRepository.findAllByOrderByOrderIndexAsc()) {
            StudentKpMastery row = masteryMap.get(point.getKpId());
            double mastery = row == null ? 0.0 : clamp(row.getMastery());
            int attempts = row == null ? 0 : row.getAttempts();
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("kpId", point.getKpId());
            item.put("kpName", point.getKpName());
            item.put("chapter", point.getChapter());
            item.put("difficulty", point.getDifficulty());
            item.put("hours", point.getHours());
            item.put("objectives", point.getObjectives());
            item.put("keyPoints", point.getKeyPoints());
            item.put("mastery", ReportMapper.round2(mastery));
            item.put("attempts", attempts);
            item.put("correctCount", row == null ? 0 : row.getCorrectCount());
            item.put("status", masteryStatus(attempts, mastery));
            result.add(item);
        }
        return result;
    }

    public static String masteryStatus(int attempts, double mastery) {
        if (attempts <= 0) {
            return "未开始";
        }
        if (mastery < WEAK_THRESHOLD) {
            return "薄弱";
        }
        if (mastery < GOOD_THRESHOLD) {
            return "一般";
        }
        return "良好";
    }

    private Map<String, StudentKpMastery> masteryMap(Long studentId) {
        Map<String, StudentKpMastery> map = new LinkedHashMap<>();
        for (StudentKpMastery row : masteryRepository.findByStudentId(studentId)) {
            map.put(row.getKpId(), row);
        }
        return map;
    }

    // ---------- S3 / S4 学习记录 ----------

    public PageResult<Map<String, Object>> records(String type, String kpId, String from, String to,
                                                   Integer page, Integer size) {
        UserInfo user = authService.currentUser();
        return recordsOf(user.getId(), type, kpId, from, to, page, size);
    }

    public PageResult<Map<String, Object>> recordsOf(Long studentId, String type, String kpId,
                                                     String from, String to, Integer page, Integer size) {
        RecordType recordType = parseRecordType(type);
        LocalDateTime fromTime = parseFrom(from);
        LocalDateTime toTime = parseTo(to);
        List<Map<String, Object>> items = new ArrayList<>();
        for (InteractionRecord record : interactionRepository.findByStudentIdOrderByCreatedAtDesc(studentId)) {
            if (recordType != null && record.getType() != recordType) {
                continue;
            }
            if (kpId != null && !kpId.isBlank()
                    && (record.getKpIds() == null || !record.getKpIds().contains(kpId))) {
                continue;
            }
            if (fromTime != null && (record.getCreatedAt() == null || record.getCreatedAt().isBefore(fromTime))) {
                continue;
            }
            if (toTime != null && (record.getCreatedAt() == null || !record.getCreatedAt().isBefore(toTime))) {
                continue;
            }
            items.add(reportMapper.recordVo(record));
        }
        return PageResult.of(items, page, size);
    }

    public Map<String, Object> recordDetail(Long id) {
        UserInfo user = authService.currentUser();
        InteractionRecord record = interactionRepository.findById(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "学习记录不存在"));
        if (!user.getId().equals(record.getStudentId())) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "学习记录不存在");
        }
        return reportMapper.recordVo(record);
    }

    // ---------- S5 / S6 报告 ----------

    public PageResult<Map<String, Object>> reports(String type, Integer page, Integer size) {
        UserInfo user = authService.currentUser();
        ReportType reportType = parseReportType(type, false);
        List<Map<String, Object>> items = new ArrayList<>();
        for (Report report : reportRepository.findByStudentIdOrderByCreatedAtDesc(user.getId())) {
            if (reportType != null && report.getType() != reportType) {
                continue;
            }
            items.add(reportMapper.reportBrief(report));
        }
        return PageResult.of(items, page, size);
    }

    public Map<String, Object> reportDetail(Long id) {
        UserInfo user = authService.currentUser();
        Report report = reportRepository.findByIdAndStudentId(id, user.getId())
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "报告不存在"));
        return reportMapper.reportVo(report);
    }

    // ---------- S7 / S8 错题 ----------

    public Map<String, Object> wrongQuestions(String kpId, String errorType, Boolean reviewed,
                                              Integer page, Integer size) {
        UserInfo user = authService.currentUser();
        List<WrongQuestion> all = wrongQuestionRepository.findByStudentIdOrderByCreatedAtDesc(user.getId());
        List<Map<String, Object>> items = new ArrayList<>();
        for (WrongQuestion question : all) {
            if (kpId != null && !kpId.isBlank() && !kpId.equals(question.getKpId())) {
                continue;
            }
            if (errorType != null && !errorType.isBlank() && !errorType.equals(question.getErrorType())) {
                continue;
            }
            if (reviewed != null && reviewed != question.isReviewed()) {
                continue;
            }
            items.add(reportMapper.wrongVo(question));
        }
        int reviewedCount = 0;
        Map<String, Integer> byErrorType = new LinkedHashMap<>();
        for (WrongQuestion question : all) {
            if (question.isReviewed()) {
                reviewedCount++;
            }
            String key = question.getErrorType() == null ? "其他" : question.getErrorType();
            byErrorType.merge(key, 1, Integer::sum);
        }
        List<Map<String, Object>> errorStats = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : byErrorType.entrySet()) {
            errorStats.add(Maps.of("errorType", entry.getKey(), "count", entry.getValue()));
        }
        PageResult<Map<String, Object>> pageResult = PageResult.of(items, page, size);
        Map<String, Object> result = new LinkedHashMap<>(Maps.of(
                "items", pageResult.items(),
                "page", pageResult.page(),
                "size", pageResult.size(),
                "total", pageResult.total(),
                "hasNext", pageResult.hasNext()));
        result.put("stats", Maps.of("total", all.size(), "reviewed", reviewedCount, "byErrorType", errorStats));
        return result;
    }

    @Transactional
    public Map<String, Object> markWrongQuestion(Long id, Boolean reviewed) {
        if (reviewed == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "reviewed 不能为空");
        }
        UserInfo user = authService.currentUser();
        WrongQuestion question = wrongQuestionRepository.findById(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "错题不存在"));
        if (!user.getId().equals(question.getStudentId())) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "错题不存在");
        }
        question.setReviewed(reviewed);
        wrongQuestionRepository.save(question);
        return reportMapper.wrongVo(question);
    }

    // ---------- 参数解析 ----------

    private RecordType parseRecordType(String type) {
        if (type == null || type.isBlank()) {
            return null;
        }
        try {
            return RecordType.valueOf(type.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "不支持的记录类型：" + type);
        }
    }

    private ReportType parseReportType(String type, boolean strict) {
        if (type == null || type.isBlank()) {
            return null;
        }
        try {
            return ReportType.valueOf(type.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            if (strict) {
                throw new BusinessException(ErrorCode.VALIDATION_ERROR, "不支持的报表类型：" + type);
            }
            return null;
        }
    }

    private LocalDateTime parseFrom(String from) {
        if (from == null || from.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(from.trim()).atStartOfDay();
        } catch (DateTimeParseException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "查询起始日期格式应为 yyyy-MM-dd");
        }
    }

    private LocalDateTime parseTo(String to) {
        if (to == null || to.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(to.trim()).plusDays(1).atStartOfDay();
        } catch (DateTimeParseException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "查询结束日期格式应为 yyyy-MM-dd");
        }
    }

    public static double clamp(double value) {
        if (value < 0) {
            return 0.0;
        }
        return Math.min(value, 1.0);
    }
}