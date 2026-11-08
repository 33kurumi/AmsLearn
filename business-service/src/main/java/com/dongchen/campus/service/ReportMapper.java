package com.dongchen.campus.service;

import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.Report;
import com.dongchen.campus.domain.WrongQuestion;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 报告 / 学习记录 / 错题 的统一对外视图。
 */
@Component
public class ReportMapper {

    private final JsonHelper jsonHelper;

    public ReportMapper(JsonHelper jsonHelper) {
        this.jsonHelper = jsonHelper;
    }

    public Map<String, Object> reportVo(Report report) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", report.getId());
        vo.put("type", report.getType() == null ? null : report.getType().name());
        vo.put("title", report.getTitle());
        vo.put("summary", report.getSummary());
        vo.put("status", report.getStatus() == null ? null : report.getStatus().name());
        vo.put("createdAt", report.getCreatedAt());
        vo.put("content", jsonHelper.readMap(report.getContent()));
        return vo;
    }

    public Map<String, Object> reportBrief(Report report) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", report.getId());
        vo.put("type", report.getType() == null ? null : report.getType().name());
        vo.put("title", report.getTitle());
        vo.put("summary", report.getSummary());
        vo.put("status", report.getStatus() == null ? null : report.getStatus().name());
        vo.put("createdAt", report.getCreatedAt());
        return vo;
    }

    public Map<String, Object> recordVo(InteractionRecord record) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", record.getId());
        vo.put("type", record.getType() == null ? null : record.getType().name());
        vo.put("intent", record.getIntent());
        vo.put("userMessage", record.getUserMessage());
        vo.put("aiResponse", record.getAiResponse());
        vo.put("sources", jsonHelper.readList(record.getSources()));
        vo.put("kpIds", jsonHelper.readList(record.getKpIds()));
        vo.put("kpNames", jsonHelper.readList(record.getKpNames()));
        vo.put("blocked", record.isBlocked());
        // v1.2：供前端「继续对话」定位会话，旧记录为 null
        vo.put("conversationId", record.getConversationId());
        vo.put("createdAt", record.getCreatedAt());
        return vo;
    }

    public Map<String, Object> wrongVo(WrongQuestion question) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", question.getId());
        vo.put("kpId", question.getKpId());
        vo.put("kpName", question.getKpName());
        vo.put("questionText", question.getQuestionText());
        vo.put("questionType", question.getQuestionType());
        vo.put("difficulty", question.getDifficulty());
        vo.put("studentAnswer", question.getStudentAnswer());
        vo.put("correctAnswer", question.getCorrectAnswer());
        vo.put("errorType", question.getErrorType());
        vo.put("analysis", question.getAnalysis());
        vo.put("sourceType", question.getSourceType());
        vo.put("reviewed", question.isReviewed());
        vo.put("createdAt", question.getCreatedAt());
        return vo;
    }

    /**
     * 计划报告 -> PlanVO。
     */
    public Map<String, Object> planVo(Report report) {
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        List<Map<String, Object>> days = new ArrayList<>();
        for (Object item : jsonHelper.toList(content.get("days"))) {
            days.add(jsonHelper.toMap(item));
        }
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", report.getId());
        vo.put("title", report.getTitle());
        vo.put("period", content.get("period"));
        vo.put("daysCount", days.size());
        vo.put("startDate", content.get("startDate"));
        vo.put("summary", content.get("summary") == null ? report.getSummary() : content.get("summary"));
        vo.put("createdAt", report.getCreatedAt());
        vo.put("days", days);
        return vo;
    }

    public Map<String, Object> planBrief(Report report) {
        List<Map<String, Object>> days = planDays(report);
        int doneDays = 0;
        for (Map<String, Object> day : days) {
            if (Boolean.TRUE.equals(day.get("done"))) {
                doneDays++;
            }
        }
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", report.getId());
        vo.put("title", report.getTitle());
        vo.put("period", content.get("period"));
        vo.put("daysCount", days.size());
        vo.put("startDate", content.get("startDate"));
        vo.put("createdAt", report.getCreatedAt());
        vo.put("progress", days.isEmpty() ? 0.0 : round2(doneDays / (double) days.size()));
        vo.put("doneDays", doneDays);
        return vo;
    }

    public List<Map<String, Object>> planDays(Report report) {
        Map<String, Object> content = jsonHelper.readMap(report.getContent());
        List<Map<String, Object>> days = new ArrayList<>();
        for (Object item : jsonHelper.toList(content.get("days"))) {
            days.add(jsonHelper.toMap(item));
        }
        return days;
    }

    public static double round2(double value) {
        return Math.round(value * 100.0) / 100.0;
    }
}
