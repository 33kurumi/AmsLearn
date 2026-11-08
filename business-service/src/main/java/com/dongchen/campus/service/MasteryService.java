package com.dongchen.campus.service;

import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.StudentKpMastery;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.dongchen.campus.repository.StudentKpMasteryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 学生知识点掌握度的读取、排序与答题后的增减。
 */
@Service
public class MasteryService {

    public static final double CORRECT_DELTA = 0.05;
    public static final double WRONG_DELTA = -0.10;

    private final StudentKpMasteryRepository masteryRepository;
    private final KnowledgePointRepository knowledgePointRepository;

    public MasteryService(StudentKpMasteryRepository masteryRepository,
                          KnowledgePointRepository knowledgePointRepository) {
        this.masteryRepository = masteryRepository;
        this.knowledgePointRepository = knowledgePointRepository;
    }

    public List<StudentKpMastery> rows(Long studentId) {
        return masteryRepository.findByStudentId(studentId);
    }

    public Map<String, KnowledgePoint> kpMap() {
        Map<String, KnowledgePoint> map = new LinkedHashMap<>();
        for (KnowledgePoint point : knowledgePointRepository.findAllByOrderByOrderIndexAsc()) {
            map.put(point.getKpId(), point);
        }
        return map;
    }

    /**
     * 掌握度最低的知识点（用于 AI 提示薄弱点），不足 67 条时按已有记录。
     */
    public List<Map<String, Object>> weakest(Long studentId, int limit) {
        Map<String, KnowledgePoint> kpMap = kpMap();
        List<StudentKpMastery> rows = new ArrayList<>(rows(studentId));
        rows.sort(Comparator.comparingDouble(StudentKpMastery::getMastery));
        List<Map<String, Object>> result = new ArrayList<>();
        for (StudentKpMastery row : rows) {
            if (result.size() >= limit) {
                break;
            }
            KnowledgePoint point = kpMap.get(row.getKpId());
            if (point == null) {
                continue;
            }
            result.add(Maps.of(
                    "kpId", row.getKpId(),
                    "kpName", point.getKpName(),
                    "mastery", ReportMapper.round2(StudentService.clamp(row.getMastery()))));
        }
        return result;
    }

    public List<Map<String, Object>> masteryList(Long studentId) {
        return weakest(studentId, Integer.MAX_VALUE);
    }

    public double avgMastery(Long studentId) {
        List<StudentKpMastery> rows = rows(studentId);
        if (rows.isEmpty()) {
            return 0.0;
        }
        double sum = 0;
        for (StudentKpMastery row : rows) {
            sum += StudentService.clamp(row.getMastery());
        }
        return ReportMapper.round2(sum / rows.size());
    }

    public int weakCount(Long studentId) {
        int count = 0;
        for (StudentKpMastery row : rows(studentId)) {
            if (StudentService.clamp(row.getMastery()) < 0.3) {
                count++;
            }
        }
        return count;
    }

    /**
     * 答对 +0.05 上限 1.0，答错 -0.1 下限 0.0，并累加作答次数。
     */
    @Transactional
    public Map<String, Object> applyAnswer(Long studentId, String kpId, boolean correct) {
        StudentKpMastery row = masteryRepository.findByStudentIdAndKpId(studentId, kpId)
                .orElseGet(() -> {
                    StudentKpMastery created = new StudentKpMastery();
                    created.setStudentId(studentId);
                    created.setKpId(kpId);
                    created.setMastery(0.0);
                    created.setAttempts(0);
                    created.setCorrectCount(0);
                    return created;
                });
        double before = StudentService.clamp(row.getMastery());
        double after = correct
                ? StudentService.clamp(before + CORRECT_DELTA)
                : StudentService.clamp(before + WRONG_DELTA);
        row.setMastery(ReportMapper.round2(after));
        row.setAttempts(row.getAttempts() + 1);
        if (correct) {
            row.setCorrectCount(row.getCorrectCount() + 1);
        }
        row.setUpdatedAt(LocalDateTime.now());
        masteryRepository.save(row);
        KnowledgePoint point = knowledgePointRepository.findById(kpId).orElse(null);
        return Maps.of(
                "kpId", kpId,
                "kpName", point == null ? kpId : point.getKpName(),
                "before", ReportMapper.round2(before),
                "after", ReportMapper.round2(after));
    }

    /**
     * 诊断报告中的 weakTop5：掌握度最低 5 个知识点 + 历史正确率。
     */
    public List<Map<String, Object>> weakTop5WithAccuracy(Long studentId) {
        Map<String, KnowledgePoint> kpMap = kpMap();
        List<StudentKpMastery> rows = new ArrayList<>(rows(studentId));
        rows.sort(Comparator.comparingDouble(StudentKpMastery::getMastery));
        List<Map<String, Object>> result = new ArrayList<>();
        for (StudentKpMastery row : rows) {
            if (result.size() >= 5) {
                break;
            }
            KnowledgePoint point = kpMap.get(row.getKpId());
            double accuracy = row.getAttempts() <= 0
                    ? 0.0
                    : ReportMapper.round2(row.getCorrectCount() / (double) row.getAttempts());
            result.add(Maps.of(
                    "kpId", row.getKpId(),
                    "kpName", point == null ? row.getKpId() : point.getKpName(),
                    "mastery", ReportMapper.round2(StudentService.clamp(row.getMastery())),
                    "accuracy", accuracy));
        }
        return result;
    }
}
