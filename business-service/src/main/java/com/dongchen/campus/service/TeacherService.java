package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.domain.AnswerMode;
import com.dongchen.campus.domain.ClassInfo;
import com.dongchen.campus.domain.ClassTeacherConfig;
import com.dongchen.campus.domain.ConfigChangeLog;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.RecordType;
import com.dongchen.campus.domain.Report;
import com.dongchen.campus.domain.ReportType;
import com.dongchen.campus.domain.Role;
import com.dongchen.campus.domain.StudentKpMastery;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.domain.WrongQuestion;
import com.dongchen.campus.repository.ClassInfoRepository;
import com.dongchen.campus.repository.ClassTeacherConfigRepository;
import com.dongchen.campus.repository.ConfigChangeLogRepository;
import com.dongchen.campus.repository.InteractionRecordRepository;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.dongchen.campus.repository.ReportRepository;
import com.dongchen.campus.repository.StudentKpMasteryRepository;
import com.dongchen.campus.repository.UserRepository;
import com.dongchen.campus.repository.WrongQuestionRepository;
import com.dongchen.campus.security.PasswordHasher;
import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 教师端业务：首页、班级配置（含留痕）、配置抽取、学情分析、学生列表与记录。
 */
@Service
public class TeacherService {

    private static final Logger log = LoggerFactory.getLogger(TeacherService.class);

    private final AuthService authService;
    private final UserMapper userMapper;
    private final ConfigService configService;
    private final StudentService studentService;
    private final MasteryService masteryService;
    private final UserRepository userRepository;
    private final ClassInfoRepository classInfoRepository;
    private final ClassTeacherConfigRepository configRepository;
    private final ConfigChangeLogRepository changeLogRepository;
    private final KnowledgePointRepository knowledgePointRepository;
    private final StudentKpMasteryRepository masteryRepository;
    private final InteractionRecordRepository interactionRepository;
    private final WrongQuestionRepository wrongQuestionRepository;
    private final ReportRepository reportRepository;
    private final AiServiceClient aiServiceClient;
    private final JsonHelper jsonHelper;
    private final PasswordHasher passwordHasher;

    public TeacherService(AuthService authService, UserMapper userMapper, ConfigService configService,
                          StudentService studentService, MasteryService masteryService,
                          UserRepository userRepository, ClassInfoRepository classInfoRepository,
                          ClassTeacherConfigRepository configRepository,
                          ConfigChangeLogRepository changeLogRepository,
                          KnowledgePointRepository knowledgePointRepository,
                          StudentKpMasteryRepository masteryRepository,
                          InteractionRecordRepository interactionRepository,
                          WrongQuestionRepository wrongQuestionRepository,
                          ReportRepository reportRepository, AiServiceClient aiServiceClient,
                          JsonHelper jsonHelper, PasswordHasher passwordHasher) {
        this.authService = authService;
        this.userMapper = userMapper;
        this.configService = configService;
        this.studentService = studentService;
        this.masteryService = masteryService;
        this.userRepository = userRepository;
        this.classInfoRepository = classInfoRepository;
        this.configRepository = configRepository;
        this.changeLogRepository = changeLogRepository;
        this.knowledgePointRepository = knowledgePointRepository;
        this.masteryRepository = masteryRepository;
        this.interactionRepository = interactionRepository;
        this.wrongQuestionRepository = wrongQuestionRepository;
        this.reportRepository = reportRepository;
        this.aiServiceClient = aiServiceClient;
        this.jsonHelper = jsonHelper;
        this.passwordHasher = passwordHasher;
    }

    // ---------- T1 首页 ----------

    public Map<String, Object> dashboard() {
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        List<UserInfo> students = userRepository.findByClassIdAndRole(classId, Role.STUDENT);
        List<Long> studentIds = students.stream().map(UserInfo::getId).toList();
        List<StudentKpMastery> rows = studentIds.isEmpty()
                ? List.of()
                : masteryRepository.findByStudentIdIn(studentIds);

        double avgMastery = 0;
        int weakStudentCount = 0;
        for (UserInfo student : students) {
            double avg = masteryService.avgMastery(student.getId());
            avgMastery += avg;
            if (avg < 0.3) {
                weakStudentCount++;
            }
        }
        if (!students.isEmpty()) {
            avgMastery = ReportMapper.round2(avgMastery / students.size());
        }
        LocalDateTime todayStart = LocalDate.now().atStartOfDay();
        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("studentCount", students.size());
        stats.put("avgMastery", avgMastery);
        stats.put("weakStudentCount", weakStudentCount);
        stats.put("interactionCount", interactionRepository.countByClassId(classId));
        stats.put("todayInteractionCount", interactionRepository.countByClassIdAndCreatedAtGreaterThanEqual(classId, todayStart));

        Map<String, KnowledgePoint> kpMap = masteryService.kpMap();
        Map<String, List<Double>> masteryByKp = new LinkedHashMap<>();
        for (StudentKpMastery row : rows) {
            masteryByKp.computeIfAbsent(row.getKpId(), key -> new ArrayList<>()).add(StudentService.clamp(row.getMastery()));
        }
        List<Map<String, Object>> weakRanked = new ArrayList<>();
        for (Map.Entry<String, List<Double>> entry : masteryByKp.entrySet()) {
            double avg = entry.getValue().stream().mapToDouble(Double::doubleValue).average().orElse(0);
            KnowledgePoint point = kpMap.get(entry.getKey());
            if (point == null) {
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("kpId", point.getKpId());
            item.put("kpName", point.getKpName());
            item.put("chapter", point.getChapter());
            item.put("mastery", ReportMapper.round2(avg));
            weakRanked.add(item);
        }
        weakRanked.sort(Comparator.comparingDouble(o -> (Double) o.get("mastery")));
        List<Map<String, Object>> weakTop5 = weakRanked.subList(0, Math.min(5, weakRanked.size()));

        List<Map<String, Object>> recentInteractions = new ArrayList<>();
        Map<Long, String> nameById = new LinkedHashMap<>();
        for (UserInfo student : students) {
            nameById.put(student.getId(), student.getDisplayName());
        }
        List<InteractionRecord> recent = interactionRepository.findByClassIdOrderByCreatedAtDesc(classId);
        int limit = Math.min(10, recent.size());
        for (int i = 0; i < limit; i++) {
            InteractionRecord record = recent.get(i);
            recentInteractions.add(Maps.of(
                    "studentName", nameById.getOrDefault(record.getStudentId(), "未知学生"),
                    "type", record.getType() == null ? null : record.getType().name(),
                    "userMessage", record.getUserMessage(),
                    "createdAt", record.getCreatedAt()));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("user", userMapper.toVo(teacher));
        result.put("classInfo", userMapper.classInfoVo(classId));
        result.put("stats", stats);
        result.put("weakTop5", weakTop5);
        result.put("recentInteractions", recentInteractions);
        result.put("knowledgeStats", knowledgeStats());
        return result;
    }

    private Map<String, Object> knowledgeStats() {
        int documents = 0;
        int chunks = 0;
        try {
            JsonNode node = aiServiceClient.health();
            documents = node.path("knowledge_documents").asInt(0);
            chunks = node.path("knowledge_chunks").asInt(0);
        } catch (BusinessException ex) {
            log.info("教师首页知识库统计获取失败：{}", ex.getMessage());
        }
        return Maps.of("documents", documents, "chunks", chunks);
    }

    // ---------- T2 / T3 / T4 / T5 班级配置 ----------

    public Map<String, Object> config() {
        UserInfo teacher = requireTeacher();
        ClassTeacherConfig config = configService.getOrCreate(requireClassId(teacher));
        return configService.toVo(config);
    }

    @Transactional
    public Map<String, Object> saveConfig(Map<String, Object> request) {
        if (request == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "请求体不能为空");
        }
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        ClassTeacherConfig config = configService.getOrCreate(classId);

        AnswerMode mode = parseAnswerMode(request.get("answerMode"));
        Integer maxDifficulty = parseMaxDifficulty(request.get("maxDifficulty"));
        Map<String, Object> scope = parseScope(request.get("knowledgeScope"));
        String boundaryRules = request.get("boundaryRules") == null ? "" : String.valueOf(request.get("boundaryRules"));
        if (boundaryRules.length() > 500) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "边界规则不能超过 500 字");
        }
        Map<String, Object> kbAccess = parseKbAccess(request.get("kbAccess"));
        List<String> disabledTopics = parseDisabledTopics(request.get("disabledTopics"));

        Map<String, Object> oldScope = configService.scopeOf(config);
        Map<String, Object> oldKb = configService.kbAccessOf(config);
        List<String> oldDisabled = configService.disabledTopicsOf(config);

        List<Map<String, Object>> changes = new ArrayList<>();
        addChange(changes, "answerMode", "答疑模式",
                config.getAnswerMode() == null ? null : config.getAnswerMode().name(), mode.name());
        addChange(changes, "maxDifficulty", "最大难度", config.getMaxDifficulty(), maxDifficulty);
        addChange(changes, "knowledgeScope", "知识范围", oldScope, scope);
        addChange(changes, "boundaryRules", "边界规则", config.getBoundaryRules(), boundaryRules);
        addChange(changes, "kbAccess", "知识库权限", oldKb, kbAccess);
        addChange(changes, "disabledTopics", "禁用话题", oldDisabled, disabledTopics);

        config.setAnswerMode(mode);
        config.setMaxDifficulty(maxDifficulty);
        config.setKnowledgeScope(jsonHelper.write(scope));
        config.setBoundaryRules(boundaryRules);
        config.setKbAccess(jsonHelper.write(kbAccess));
        config.setDisabledTopics(jsonHelper.write(disabledTopics));
        config.setUpdatedAt(LocalDateTime.now());
        config.setUpdatedBy(teacher.getId());
        configRepository.save(config);

        if (!changes.isEmpty()) {
            List<String> labels = new ArrayList<>();
            for (Map<String, Object> change : changes) {
                labels.add(String.valueOf(change.get("label")));
            }
            ConfigChangeLog log = new ConfigChangeLog();
            log.setClassId(classId);
            log.setChangedBy(teacher.getId());
            log.setChangedByName(teacher.getDisplayName());
            log.setSummary("修改班级教学配置（" + String.join("、", labels) + "）");
            log.setChanges(jsonHelper.write(changes));
            log.setChangedAt(LocalDateTime.now());
            changeLogRepository.save(log);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("config", configService.toVo(config));
        result.put("changes", changes);
        result.put("effectNote", "配置已保存，对后续所有请求立即生效。");
        return result;
    }

    public PageResult<Map<String, Object>> configLogs(Integer page, Integer size) {
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        List<Map<String, Object>> items = new ArrayList<>();
        for (ConfigChangeLog log : changeLogRepository.findByClassIdOrderByChangedAtDesc(classId)) {
            items.add(Maps.of(
                    "id", log.getId(),
                    "changedAt", log.getChangedAt(),
                    "changedByName", log.getChangedByName(),
                    "summary", log.getSummary(),
                    "changes", jsonHelper.readList(log.getChanges())));
        }
        return PageResult.of(items, page, size);
    }

    public Map<String, Object> extractConfig(String text) {
        if (text == null || text.isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "待抽取的配置描述不能为空");
        }
        UserInfo teacher = requireTeacher();
        ClassTeacherConfig config = configService.getOrCreate(requireClassId(teacher));
        JsonNode node = aiServiceClient.configExtract(Maps.of(
                "text", text.trim(),
                "current", configService.toVo(config)));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("patch", jsonHelper.toMap(node.get("patch")));
        result.put("explanation", jsonHelper.nodeText(node, "explanation", ""));
        result.put("unrecognized", jsonHelper.toList(jsonHelper.mapper().convertValue(node.path("unrecognized"), Object.class)));
        result.put("mode", jsonHelper.nodeText(node, "mode", ""));
        return result;
    }

    // ---------- T6 学情分析 ----------

    public Map<String, Object> analysis(String period) {
        String queryPeriod = normalizePeriod(period);
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        ClassInfo classInfo = classInfoRepository.findById(classId).orElse(null);
        LocalDateTime from = periodStart(queryPeriod);

        List<UserInfo> students = userRepository.findByClassIdAndRole(classId, Role.STUDENT);
        List<Long> studentIds = students.stream().map(UserInfo::getId).toList();
        Map<Long, UserInfo> studentById = new LinkedHashMap<>();
        for (UserInfo student : students) {
            studentById.put(student.getId(), student);
        }
        List<StudentKpMastery> masteryRows = studentIds.isEmpty()
                ? List.of()
                : masteryRepository.findByStudentIdIn(studentIds);
        List<InteractionRecord> interactions = interactionRepository
                .findByClassIdAndCreatedAtGreaterThanEqualOrderByCreatedAtDesc(classId, from);
        List<WrongQuestion> wrongQuestions = wrongQuestionRepository.findByClassIdAndCreatedAtGreaterThanEqual(classId, from);
        List<Report> diagnoses = reportRepository.findByClassIdAndTypeAndCreatedAtGreaterThanEqual(
                classId, ReportType.DIAGNOSIS, from);

        double masterySum = 0;
        Map<String, List<Double>> byKp = new LinkedHashMap<>();
        for (StudentKpMastery row : masteryRows) {
            double mastery = StudentService.clamp(row.getMastery());
            masterySum += mastery;
            byKp.computeIfAbsent(row.getKpId(), key -> new ArrayList<>()).add(mastery);
        }
        double avgMastery = masteryRows.isEmpty() ? 0 : ReportMapper.round2(masterySum / masteryRows.size());
        int[] bins = new int[5];
        for (List<Double> values : byKp.values()) {
            double kpAvg = values.stream().mapToDouble(Double::doubleValue).average().orElse(0);
            bins[Math.min(4, Math.max(0, (int) Math.floor(kpAvg * 5)))]++;
        }
        String[] ranges = {"0-20%", "20-40%", "40-60%", "60-80%", "80-100%"};
        List<Map<String, Object>> masteryDistribution = new ArrayList<>();
        for (int i = 0; i < ranges.length; i++) {
            masteryDistribution.add(Maps.of("range", ranges[i], "count", bins[i]));
        }

        Map<String, KnowledgePoint> kpMap = masteryService.kpMap();
        List<Map<String, Object>> weakRanked = new ArrayList<>();
        for (Map.Entry<String, List<Double>> entry : byKp.entrySet()) {
            KnowledgePoint point = kpMap.get(entry.getKey());
            if (point == null) {
                continue;
            }
            double avg = entry.getValue().stream().mapToDouble(Double::doubleValue).average().orElse(0);
            int weakStudents = (int) entry.getValue().stream().filter(value -> value < 0.3).count();
            weakRanked.add(Maps.of(
                    "kpId", point.getKpId(),
                    "kpName", point.getKpName(),
                    "chapter", point.getChapter(),
                    "avgMastery", ReportMapper.round2(avg),
                    "studentCount", weakStudents));
        }
        weakRanked.sort(Comparator.comparingDouble(o -> (Double) o.get("avgMastery")));
        List<Map<String, Object>> weakTop10 = weakRanked.subList(0, Math.min(10, weakRanked.size()));

        Map<String, List<WrongQuestion>> wrongByType = new LinkedHashMap<>();
        for (WrongQuestion question : wrongQuestions) {
            String key = question.getErrorType() == null ? "其他" : question.getErrorType();
            wrongByType.computeIfAbsent(key, k -> new ArrayList<>()).add(question);
        }
        List<Map<String, Object>> errorSummary = new ArrayList<>();
        for (Map.Entry<String, List<WrongQuestion>> entry : wrongByType.entrySet()) {
            List<String> examples = new ArrayList<>();
            for (WrongQuestion question : entry.getValue()) {
                if (examples.size() >= 3) {
                    break;
                }
                if (question.getQuestionText() != null) {
                    examples.add(question.getQuestionText());
                }
            }
            double ratio = wrongQuestions.isEmpty()
                    ? 0
                    : ReportMapper.round2(entry.getValue().size() / (double) wrongQuestions.size());
            errorSummary.add(Maps.of(
                    "errorType", entry.getKey(),
                    "count", entry.getValue().size(),
                    "ratio", ratio,
                    "examples", examples));
        }
        errorSummary.sort(Comparator.comparingInt(o -> -((Integer) o.get("count"))));

        Map<String, int[]> hotCounter = new LinkedHashMap<>();
        Map<String, LocalDateTime> hotLast = new LinkedHashMap<>();
        for (InteractionRecord record : interactions) {
            if (record.getType() != RecordType.QA || record.getUserMessage() == null) {
                continue;
            }
            String question = record.getUserMessage().trim();
            hotCounter.computeIfAbsent(question, k -> new int[1])[0]++;
            LocalDateTime last = hotLast.get(question);
            if (last == null || (record.getCreatedAt() != null && record.getCreatedAt().isAfter(last))) {
                hotLast.put(question, record.getCreatedAt());
            }
        }
        List<Map<String, Object>> rankedHot = new ArrayList<>();
        for (Map.Entry<String, int[]> entry : hotCounter.entrySet()) {
            rankedHot.add(Maps.of(
                    "question", entry.getKey(),
                    "count", entry.getValue()[0],
                    "lastAskedAt", hotLast.get(entry.getKey())));
        }
        rankedHot.sort(Comparator.comparingInt(o -> -((Integer) o.get("count"))));
        List<Map<String, Object>> hotQuestions = rankedHot.subList(0, Math.min(10, rankedHot.size()));

        Map<Long, Integer> interactionCounts = new LinkedHashMap<>();
        Set<Long> activeStudents = new LinkedHashSet<>();
        for (InteractionRecord record : interactions) {
            if (record.getStudentId() == null) {
                continue;
            }
            interactionCounts.merge(record.getStudentId(), 1, Integer::sum);
            activeStudents.add(record.getStudentId());
        }
        List<Map<String, Object>> ranking = new ArrayList<>();
        for (UserInfo student : students) {
            ranking.add(Maps.of(
                    "studentId", student.getId(),
                    "displayName", student.getDisplayName(),
                    "mastery", masteryService.avgMastery(student.getId()),
                    "interactions", interactionCounts.getOrDefault(student.getId(), 0)));
        }
        ranking.sort(Comparator
                .comparingDouble((Map<String, Object> o) -> -((Double) o.get("mastery")))
                .thenComparingInt(o -> -((Integer) o.get("interactions"))));

        int correctTotal = 0;
        int answeredTotal = 0;
        for (Report report : diagnoses) {
            Map<String, Object> content = jsonHelper.readMap(report.getContent());
            correctTotal += toInt(content.get("correctCount"));
            answeredTotal += toInt(content.get("total"));
        }
        double accuracy = answeredTotal == 0 ? 0.0 : ReportMapper.round2(correctTotal / (double) answeredTotal);

        Map<String, Object> overview = new LinkedHashMap<>();
        overview.put("studentCount", students.size());
        overview.put("avgMastery", avgMastery);
        overview.put("interactionCount", interactions.size());
        overview.put("activeStudents", activeStudents.size());
        overview.put("accuracy", accuracy);

        Map<String, Object> aiBody = new LinkedHashMap<>();
        aiBody.put("period", queryPeriod);
        aiBody.put("classId", classId);
        aiBody.put("className", classInfo == null ? null : classInfo.getClassName());
        aiBody.put("subject", classInfo == null ? null : classInfo.getSubject());
        aiBody.put("studentCount", students.size());
        aiBody.put("totalInteractions", interactions.size());
        aiBody.put("activeStudents", activeStudents.size());
        aiBody.put("accuracy", accuracy);
        aiBody.put("masteryDistribution", masteryDistribution);
        aiBody.put("weakKps", weakTop10);
        aiBody.put("errorStats", errorSummary);
        aiBody.put("hotQuestions", hotQuestions);
        aiBody.put("ranking", ranking);

        List<Object> advice = new ArrayList<>();
        String summary = "";
        boolean aiOk = false;
        try {
            JsonNode node = aiServiceClient.classAnalysis(aiBody);
            advice = jsonHelper.toList(jsonHelper.mapper().convertValue(node.path("advice"), Object.class));
            summary = jsonHelper.nodeText(node, "summary", "");
            aiOk = true;
        } catch (BusinessException ex) {
            log.info("学情分析 AI 调用失败，使用规则兜底：{}", ex.getMessage());
        }
        if (!aiOk || advice.isEmpty()) {
            advice = ruleAdvice(weakTop10, weakStudentCount(classId, students), errorSummary);
        }
        if (summary == null || summary.isBlank()) {
            summary = "近" + periodLabel(queryPeriod) + "班级共 " + students.size() + " 名学生，平均掌握度 "
                    + avgMastery + "，互动 " + interactions.size() + " 次；建议优先突破 "
                    + Math.min(5, weakTop10.size()) + " 个薄弱知识点。";
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("period", queryPeriod);
        result.put("generatedAt", LocalDateTime.now());
        result.put("overview", overview);
        result.put("masteryDistribution", masteryDistribution);
        result.put("weakTop10", weakTop10);
        result.put("errorSummary", errorSummary);
        result.put("hotQuestions", hotQuestions);
        result.put("ranking", ranking);
        result.put("advice", advice);
        result.put("summary", summary);
        return result;
    }

    private int weakStudentCount(String classId, List<UserInfo> students) {
        int count = 0;
        for (UserInfo student : students) {
            if (masteryService.avgMastery(student.getId()) < 0.3) {
                count++;
            }
        }
        return count;
    }

    private List<Object> ruleAdvice(List<Map<String, Object>> weakTop10, int weakStudentCount,
                                    List<Map<String, Object>> errorSummary) {
        List<Object> advice = new ArrayList<>();
        if (!weakTop10.isEmpty()) {
            List<String> names = new ArrayList<>();
            for (Map<String, Object> item : weakTop10) {
                if (names.size() >= 3) {
                    break;
                }
                names.add(String.valueOf(item.get("kpName")));
            }
            advice.add(Maps.of(
                    "title", "优先补齐薄弱知识点",
                    "content", "建议针对 " + String.join("、", names) + " 等知识点安排专项讲解与分层练习，并在下次课前提问检查。",
                    "priority", "高"));
        }
        if (weakStudentCount > 0) {
            advice.add(Maps.of(
                    "title", "关注掌握度偏低的学生",
                    "content", "班级中有 " + weakStudentCount + " 名学生平均掌握度低于 30%，建议结合学习计划逐一沟通。",
                    "priority", "中"));
        }
        if (!errorSummary.isEmpty()) {
            Map<String, Object> top = errorSummary.get(0);
            advice.add(Maps.of(
                    "title", "针对高频错误类型强化训练",
                    "content", "错题中「" + top.get("errorType") + "」出现 " + top.get("count") + " 次，建议设计同类变式题集中训练。",
                    "priority", "中"));
        }
        if (advice.isEmpty()) {
            advice.add(Maps.of("title", "保持当前节奏", "content", "班级整体掌握度平稳，建议按计划推进并定期诊断。", "priority", "低"));
        }
        return advice;
    }

    // ---------- T7 / T8 学生 ----------

    public List<Map<String, Object>> students() {
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        List<Map<String, Object>> result = new ArrayList<>();
        for (UserInfo student : userRepository.findByClassIdAndRole(classId, Role.STUDENT)) {
            InteractionRecord last = interactionRepository.findFirstByStudentIdOrderByCreatedAtDesc(student.getId()).orElse(null);
            result.add(Maps.of(
                    "id", student.getId(),
                    "username", student.getUsername(),
                    "displayName", student.getDisplayName(),
                    "mastery", masteryService.avgMastery(student.getId()),
                    "weakCount", masteryService.weakCount(student.getId()),
                    "interactionCount", interactionRepository.countByStudentId(student.getId()),
                    "lastActiveAt", last == null ? null : last.getCreatedAt()));
        }
        return result;
    }

    public PageResult<Map<String, Object>> studentRecords(Long studentId, String type, String kpId,
                                                          String from, String to, Integer page, Integer size) {
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        UserInfo student = userRepository.findById(studentId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "学生不存在"));
        if (student.getRole() != Role.STUDENT || !classId.equals(student.getClassId())) {
            throw new BusinessException(ErrorCode.FORBIDDEN, "无权查看其他班级学生的数据");
        }
        return studentService.recordsOf(studentId, type, kpId, from, to, page, size);
    }

    /**
     * v1.4 教师重置本班学生密码：立即生效（新密码可直接登录，旧密码失效）。
     */
    @Transactional
    public void resetStudentPassword(Long studentId, String newPassword) {
        UserInfo teacher = requireTeacher();
        String classId = requireClassId(teacher);
        if (newPassword == null || newPassword.length() < 6 || newPassword.length() > 32) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "newPassword 新密码长度应为 6~32 位");
        }
        UserInfo student = userRepository.findById(studentId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "学生不存在"));
        if (student.getRole() != Role.STUDENT || !classId.equals(student.getClassId())) {
            throw new BusinessException(ErrorCode.FORBIDDEN, "只能重置本班学生的密码");
        }
        student.setPasswordHash(passwordHasher.hash(newPassword));
        userRepository.save(student);
    }

    // ---------- 参数解析与工具 ----------

    private UserInfo requireTeacher() {
        UserInfo user = authService.currentUser();
        if (user.getRole() != Role.TEACHER) {
            throw new BusinessException(ErrorCode.FORBIDDEN, "仅教师可访问该接口");
        }
        if (user.getClassId() == null || user.getClassId().isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "当前教师未绑定班级");
        }
        return user;
    }

    private String requireClassId(UserInfo teacher) {
        if (teacher.getClassId() == null || teacher.getClassId().isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "当前教师未绑定班级");
        }
        return teacher.getClassId();
    }

    private AnswerMode parseAnswerMode(Object value) {
        if (value == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "答疑模式不能为空");
        }
        try {
            return AnswerMode.valueOf(String.valueOf(value).trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "答疑模式仅支持 GUIDED/DIRECT/MIXED");
        }
    }

    private Integer parseMaxDifficulty(Object value) {
        Integer difficulty = value instanceof Number number ? number.intValue() : null;
        if (difficulty == null) {
            try {
                difficulty = Integer.parseInt(String.valueOf(value));
            } catch (NumberFormatException ex) {
                throw new BusinessException(ErrorCode.VALIDATION_ERROR, "最大难度应为 1~4 的整数");
            }
        }
        if (difficulty < 1 || difficulty > 4) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "最大难度应在 1~4 之间");
        }
        return difficulty;
    }

    private Map<String, Object> parseScope(Object value) {
        Map<String, Object> scope = jsonHelper.toMap(value);
        Object modeValue = scope.get("mode");
        if (modeValue == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "知识范围模式不能为空");
        }
        String mode = String.valueOf(modeValue).trim().toUpperCase();
        if (!"ALL".equals(mode) && !"CHAPTER".equals(mode) && !"CUSTOM".equals(mode)) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "知识范围模式仅支持 ALL/CHAPTER/CUSTOM");
        }
        List<Object> chapters = jsonHelper.toList(scope.get("chapters"));
        List<Object> kpIds = jsonHelper.toList(scope.get("kpIds"));
        if ("CHAPTER".equals(mode) && chapters.isEmpty()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "章节范围模式需要至少选择一个章节");
        }
        if ("CUSTOM".equals(mode) && kpIds.isEmpty()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "知识点范围模式需要至少选择一个知识点");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", mode);
        result.put("chapters", chapters);
        result.put("kpIds", kpIds);
        return result;
    }

    private Map<String, Object> parseKbAccess(Object value) {
        Map<String, Object> kb = jsonHelper.toMap(value);
        if (kb.isEmpty()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "知识库权限不能为空");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (String key : List.of("kb1", "kb2", "kb3", "kb4")) {
            Object flag = kb.get(key);
            if (flag == null) {
                throw new BusinessException(ErrorCode.VALIDATION_ERROR, "知识库权限缺少 " + key);
            }
            result.put(key, Boolean.parseBoolean(String.valueOf(flag)));
        }
        return result;
    }

    private List<String> parseDisabledTopics(Object value) {
        List<String> topics = new ArrayList<>();
        for (Object item : jsonHelper.toList(value)) {
            if (item != null && !String.valueOf(item).isBlank()) {
                topics.add(String.valueOf(item).trim());
            }
        }
        return topics;
    }

    private void addChange(List<Map<String, Object>> changes, String field, String label,
                           Object before, Object after) {
        if (jsonHelper.write(before).equals(jsonHelper.write(after))) {
            return;
        }
        changes.add(Maps.of("field", field, "label", label, "before", before, "after", after));
    }

    private String normalizePeriod(String period) {
        if (period == null || period.isBlank()) {
            return "30D";
        }
        String value = period.trim().toUpperCase();
        if (!"7D".equals(value) && !"30D".equals(value) && !"TERM".equals(value)) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "统计周期仅支持 7D/30D/TERM");
        }
        return value;
    }

    private LocalDateTime periodStart(String period) {
        return switch (period) {
            case "7D" -> LocalDateTime.now().minusDays(7);
            case "TERM" -> LocalDateTime.now().minusDays(120);
            default -> LocalDateTime.now().minusDays(30);
        };
    }

    private String periodLabel(String period) {
        return switch (period) {
            case "7D" -> "7 天";
            case "TERM" -> "本学期";
            default -> "30 天";
        };
    }

    private int toInt(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value == null) {
            return 0;
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException ex) {
            return 0;
        }
    }
}
