package com.dongchen.campus.service;

import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.AnswerMode;
import com.dongchen.campus.domain.ClassInfo;
import com.dongchen.campus.domain.ClassTeacherConfig;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.ClassInfoRepository;
import com.dongchen.campus.repository.ClassTeacherConfigRepository;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.dongchen.campus.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 班级教师配置的读取、解析（knowledgeScope -> effectiveKpIds）与对外视图。
 */
@Service
public class ConfigService {

    public static final String BOUNDARY_RULES =
            "仅解答高等数学（考研数学一/二/三）范围内内容；不提供作业与考试的最终答案；不讨论无关话题。";

    private final ClassTeacherConfigRepository configRepository;
    private final ClassInfoRepository classInfoRepository;
    private final KnowledgePointRepository knowledgePointRepository;
    private final UserRepository userRepository;
    private final JsonHelper jsonHelper;

    public ConfigService(ClassTeacherConfigRepository configRepository,
                         ClassInfoRepository classInfoRepository,
                         KnowledgePointRepository knowledgePointRepository,
                         UserRepository userRepository,
                         JsonHelper jsonHelper) {
        this.configRepository = configRepository;
        this.classInfoRepository = classInfoRepository;
        this.knowledgePointRepository = knowledgePointRepository;
        this.userRepository = userRepository;
        this.jsonHelper = jsonHelper;
    }

    @Transactional
    public ClassTeacherConfig getOrCreate(String classId) {
        return configRepository.findByClassId(classId).orElseGet(() -> {
            ClassInfo info = classInfoRepository.findById(classId).orElse(null);
            ClassTeacherConfig config = new ClassTeacherConfig();
            config.setClassId(classId);
            config.setAnswerMode(AnswerMode.GUIDED);
            config.setMaxDifficulty(2);
            config.setKnowledgeScope(jsonHelper.write(defaultScope()));
            config.setBoundaryRules(BOUNDARY_RULES);
            config.setKbAccess(jsonHelper.write(Maps.of("kb1", true, "kb2", true, "kb3", true, "kb4", false)));
            config.setDisabledTopics("[]");
            config.setUpdatedAt(LocalDateTime.now());
            config.setUpdatedBy(info == null ? null : info.getTeacherId());
            return configRepository.save(config);
        });
    }

    public Map<String, Object> defaultScope() {
        return Maps.of("mode", "ALL", "chapters", List.of(), "kpIds", List.of());
    }

    public Map<String, Object> defaultKbAccess() {
        return Maps.of("kb1", true, "kb2", true, "kb3", true, "kb4", false);
    }

    public Map<String, Object> scopeOf(ClassTeacherConfig config) {
        Map<String, Object> scope = jsonHelper.readMap(config.getKnowledgeScope());
        if (scope.isEmpty()) {
            return defaultScope();
        }
        if (scope.get("mode") == null) {
            scope.put("mode", "ALL");
        }
        if (!(scope.get("chapters") instanceof List)) {
            scope.put("chapters", List.of());
        }
        if (!(scope.get("kpIds") instanceof List)) {
            scope.put("kpIds", List.of());
        }
        return scope;
    }

    public Map<String, Object> kbAccessOf(ClassTeacherConfig config) {
        Map<String, Object> kb = jsonHelper.readMap(config.getKbAccess());
        if (kb.isEmpty()) {
            return defaultKbAccess();
        }
        for (String key : List.of("kb1", "kb2", "kb3", "kb4")) {
            kb.putIfAbsent(key, Boolean.FALSE);
        }
        return kb;
    }

    public List<String> disabledTopicsOf(ClassTeacherConfig config) {
        return jsonHelper.readStringList(config.getDisabledTopics());
    }

    /**
     * 解析知识范围为具体知识点 ID。ALL 返回空列表（表示不限制）。
     */
    public List<String> effectiveKpIds(ClassTeacherConfig config) {
        Map<String, Object> scope = scopeOf(config);
        String mode = String.valueOf(scope.get("mode"));
        if ("ALL".equalsIgnoreCase(mode)) {
            return new ArrayList<>();
        }
        List<KnowledgePoint> points = knowledgePointRepository.findAllByOrderByOrderIndexAsc();
        if ("CHAPTER".equalsIgnoreCase(mode)) {
            List<Object> chapters = jsonHelper.toList(scope.get("chapters"));
            List<String> chapterNames = new ArrayList<>();
            for (Object chapter : chapters) {
                chapterNames.add(String.valueOf(chapter));
            }
            List<String> result = new ArrayList<>();
            for (KnowledgePoint point : points) {
                if (chapterNames.contains(point.getChapter())) {
                    result.add(point.getKpId());
                }
            }
            return result;
        }
        List<Object> kpIds = jsonHelper.toList(scope.get("kpIds"));
        List<String> result = new ArrayList<>();
        List<String> existing = points.stream().map(KnowledgePoint::getKpId).toList();
        for (Object kpId : kpIds) {
            String id = String.valueOf(kpId);
            if (existing.contains(id)) {
                result.add(id);
            }
        }
        return result;
    }

    public Map<String, Object> aiTeacherConfig(ClassTeacherConfig config) {
        return Maps.of(
                "answerMode", config.getAnswerMode() == null ? "GUIDED" : config.getAnswerMode().name(),
                "maxDifficulty", config.getMaxDifficulty(),
                "effectiveKpIds", effectiveKpIds(config),
                "boundaryRules", config.getBoundaryRules(),
                "disabledTopics", disabledTopicsOf(config),
                "kbAccess", kbAccessOf(config));
    }

    public Map<String, Object> toVo(ClassTeacherConfig config) {
        ClassInfo info = classInfoRepository.findById(config.getClassId()).orElse(null);
        UserInfo updater = config.getUpdatedBy() == null
                ? null
                : userRepository.findById(config.getUpdatedBy()).orElse(null);
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("classId", config.getClassId());
        vo.put("className", info == null ? null : info.getClassName());
        vo.put("subject", info == null ? null : info.getSubject());
        vo.put("teacherId", info == null ? null : info.getTeacherId());
        vo.put("teacherName", info == null ? null : info.getTeacherName());
        vo.put("answerMode", config.getAnswerMode() == null ? null : config.getAnswerMode().name());
        vo.put("maxDifficulty", config.getMaxDifficulty());
        vo.put("knowledgeScope", scopeOf(config));
        vo.put("boundaryRules", config.getBoundaryRules());
        vo.put("kbAccess", kbAccessOf(config));
        vo.put("disabledTopics", disabledTopicsOf(config));
        vo.put("updatedAt", config.getUpdatedAt());
        vo.put("updatedByName", updater == null ? null : updater.getDisplayName());
        return vo;
    }
}
