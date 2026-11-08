package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.ClassTeacherConfig;
import com.dongchen.campus.domain.Conversation;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.RecordType;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.InteractionRecordRepository;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * S9 智能答疑：调用 AI 服务 /qa，并留存交互记录。
 * v1.2：支持会话（conversationId）、最近 6 条上下文 history、用户自有 Key 覆盖与 AI 模式回显。
 */
@Service
public class ChatService {

    /** v1.3 图片答疑限制：≤5MB，png/jpeg/webp/gif */
    private static final long MAX_VISION_BYTES = 5L * 1024 * 1024;
    private static final Set<String> VISION_CONTENT_TYPES =
            Set.of("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif");
    private static final Set<String> VISION_EXTENSIONS =
            Set.of(".png", ".jpg", ".jpeg", ".webp", ".gif");

    private final AuthService authService;
    private final ConfigService configService;
    private final MasteryService masteryService;
    private final InteractionRecordRepository interactionRepository;
    private final AiServiceClient aiServiceClient;
    private final JsonHelper jsonHelper;
    private final ConversationService conversationService;
    private final ProfileAiService profileAiService;

    public ChatService(AuthService authService, ConfigService configService,
                       MasteryService masteryService,
                       InteractionRecordRepository interactionRepository,
                       AiServiceClient aiServiceClient, JsonHelper jsonHelper,
                       ConversationService conversationService, ProfileAiService profileAiService) {
        this.authService = authService;
        this.configService = configService;
        this.masteryService = masteryService;
        this.interactionRepository = interactionRepository;
        this.aiServiceClient = aiServiceClient;
        this.jsonHelper = jsonHelper;
        this.conversationService = conversationService;
        this.profileAiService = profileAiService;
    }

    @Transactional
    public Map<String, Object> chat(String message, Object rawConversationId) {
        if (message == null || message.isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "提问内容不能为空");
        }
        UserInfo user = authService.currentUser();
        Long requestedConversationId = parseConversationId(rawConversationId);

        Conversation conversation;
        List<Map<String, Object>> history;
        if (requestedConversationId == null) {
            conversation = conversationService.createForChat(user, message);
            history = List.of();
        } else {
            conversation = conversationService.requireOwned(requestedConversationId);
            history = conversationService.history(conversation.getId());
        }

        ClassTeacherConfig config = configService.getOrCreate(user.getClassId());
        Map<String, KnowledgePoint> kpMap = masteryService.kpMap();
        List<Map<String, Object>> mastery = masteryService.weakest(user.getId(), 20);

        Map<String, Object> body = Maps.of(
                "userId", user.getId(),
                "role", user.getRole().name(),
                "classId", user.getClassId(),
                "conversationId", String.valueOf(conversation.getId()),
                "message", message.trim(),
                "history", history,
                "teacherConfig", configService.aiTeacherConfig(config),
                "mastery", mastery);
        Map<String, Object> llm = profileAiService.effectiveLlm(user);
        if (llm != null) {
            body.put("llm", llm);
        }
        JsonNode node = aiServiceClient.qa(body);

        String reply = jsonHelper.nodeText(node, "answer", "");
        String intent = jsonHelper.nodeText(node, "intent", "unknown");
        boolean blocked = node.path("blocked").asBoolean(false);
        String blockReason = jsonHelper.nodeText(node, "blockReason", null);
        // AI 服务 /qa v1.1 新增字段：知识覆盖标记（默认 true）与超出范围的提示文案（可为 null）
        boolean knowledgeCovered = !node.has("knowledgeCovered") || node.get("knowledgeCovered").asBoolean(true);
        String scopeWarning = jsonHelper.nodeText(node, "scopeWarning", null);
        // v1.3：教师超纲 → AI 返回 gate（前置自测），透传前端并落库
        Object gate = toObject(node, "gate");
        // v1.2：AI 模式与模型来源（system | user | mock）
        String mode = jsonHelper.nodeText(node, "mode", "mock");
        String model = jsonHelper.nodeText(node, "model", null);
        String modelSource = jsonHelper.nodeText(node, "modelSource", null);
        if (modelSource == null || modelSource.isBlank()) {
            modelSource = "real".equalsIgnoreCase(mode) ? "system" : "mock";
        }
        Map<String, Object> action = jsonHelper.toMap(node.get("action"));
        List<Object> sources = jsonHelper.toList(jsonHelper.mapper().convertValue(
                node.path("sources"), Object.class));
        List<String> kpIds = jsonHelper.toStringList(node.get("kpIds"));
        List<String> kpNames = new ArrayList<>();
        for (String kpId : kpIds) {
            KnowledgePoint point = kpMap.get(kpId);
            if (point != null) {
                kpNames.add(point.getKpName());
            }
        }
        if (kpNames.isEmpty()) {
            for (Object source : sources) {
                Map<String, Object> sourceMap = jsonHelper.toMap(source);
                Object kpId = sourceMap.get("kpId");
                KnowledgePoint point = kpId == null ? null : kpMap.get(String.valueOf(kpId));
                if (point != null && !kpNames.contains(point.getKpName())) {
                    kpNames.add(point.getKpName());
                }
            }
        }

        InteractionRecord record = new InteractionRecord();
        record.setStudentId(user.getId());
        record.setClassId(user.getClassId());
        record.setConversationId(conversation.getId());
        record.setType(RecordType.QA);
        record.setIntent(intent);
        record.setUserMessage(message.trim());
        record.setAiResponse(reply);
        record.setSources(jsonHelper.write(sources));
        record.setKpIds(jsonHelper.write(kpIds));
        record.setKpNames(jsonHelper.write(kpNames));
        record.setBlocked(blocked);
        record.setBlockReason(blockReason);
        record.setKnowledgeCovered(knowledgeCovered);
        record.setScopeWarning(scopeWarning);
        record.setGateJson(gate == null ? null : jsonHelper.write(gate));
        record.setCreatedAt(LocalDateTime.now());
        interactionRepository.save(record);
        // 一问一答两条消息，刷新会话统计与更新时间
        conversationService.touch(conversation.getId(), 2);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("recordId", record.getId());
        result.put("conversationId", conversation.getId());
        result.put("reply", reply);
        result.put("intent", intent);
        result.put("action", action.isEmpty() ? Maps.of("type", "NONE", "label", "", "params", null) : action);
        result.put("sources", sources);
        result.put("blocked", blocked);
        result.put("blockReason", blockReason);
        result.put("knowledgeCovered", knowledgeCovered);
        result.put("scopeWarning", scopeWarning);
        result.put("gate", gate);
        result.put("kpNames", kpNames);
        result.put("mode", mode);
        result.put("model", model);
        result.put("modelSource", modelSource);
        result.put("createdAt", record.getCreatedAt());
        return result;
    }

    /** v1.3 图片答疑：校验图片类型/大小后转发 AI /vision/extract，data 原样返回识别结果。 */
    public Map<String, Object> visionExtract(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "请上传图片文件");
        }
        if (file.getSize() > MAX_VISION_BYTES) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "图片大小不能超过 5MB");
        }
        if (!isSupportedImage(file)) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "仅支持 png/jpeg/webp/gif 格式的图片");
        }
        JsonNode node = aiServiceClient.visionExtract(file);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", node.path("ok").asBoolean(false));
        result.put("text", jsonHelper.nodeText(node, "text", ""));
        result.put("model", jsonHelper.nodeText(node, "model", null));
        result.put("provider", jsonHelper.nodeText(node, "provider", null));
        result.put("message", jsonHelper.nodeText(node, "message", null));
        return result;
    }

    /** v1.3 前置自测提交：转发 AI /qa/gate/check，落一条问答记录（会话内表现为 user + assistant 两条消息）。 */
    @Transactional
    public Map<String, Object> gateCheck(String gateId, Object rawConversationId,
                                         List<Map<String, Object>> answers) {
        if (gateId == null || gateId.isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "gateId 不能为空");
        }
        if (answers == null || answers.isEmpty()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "请提交前置测试答案");
        }
        Long conversationId = parseConversationId(rawConversationId);
        if (conversationId == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "conversationId 不能为空");
        }
        UserInfo user = authService.currentUser();
        conversationService.requireOwned(conversationId);

        Map<String, Object> body = Maps.of(
                "gateId", gateId,
                "conversationId", String.valueOf(conversationId),
                "answers", answers);
        JsonNode node = aiServiceClient.gateCheck(body);

        boolean passed = node.path("passed").asBoolean(false);
        int score = node.path("score").asInt(0);
        int total = node.path("total").asInt(0);
        String state = jsonHelper.nodeText(node, "state", passed ? "PASSED" : "FAILED");
        String feedback = jsonHelper.nodeText(node, "feedback", "");
        String answer = jsonHelper.nodeText(node, "answer", "");
        List<Object> sources = toObjectList(node, "sources");
        boolean knowledgeCovered = !node.has("knowledgeCovered") || node.get("knowledgeCovered").asBoolean(true);
        Object gate = toObject(node, "gate");
        Object teaching = toObject(node, "teaching");
        String mode = jsonHelper.nodeText(node, "mode", "mock");
        String model = jsonHelper.nodeText(node, "model", null);
        String modelSource = jsonHelper.nodeText(node, "modelSource", null);
        if (modelSource == null || modelSource.isBlank()) {
            modelSource = "real".equalsIgnoreCase(mode) ? "system" : "mock";
        }

        String aiResponse = passed ? answer : feedback;
        if (aiResponse == null || aiResponse.isBlank()) {
            aiResponse = passed ? "前置测试已通过，开始循序渐进学习。" : "前置测试未通过，请先巩固前置知识。";
        }
        InteractionRecord record = new InteractionRecord();
        record.setStudentId(user.getId());
        record.setClassId(user.getClassId());
        record.setConversationId(conversationId);
        record.setType(RecordType.QA);
        record.setIntent("qa");
        record.setUserMessage("前置测试提交（" + answers.size() + " 题）");
        record.setAiResponse(aiResponse);
        record.setSources(jsonHelper.write(sources));
        record.setKpIds(jsonHelper.write(gatePrerequisites(gate, "kpId")));
        record.setKpNames(jsonHelper.write(gatePrerequisites(gate, "kpName")));
        record.setBlocked(false);
        record.setKnowledgeCovered(knowledgeCovered);
        record.setGateJson(gate == null ? null : jsonHelper.write(gate));
        record.setCreatedAt(LocalDateTime.now());
        interactionRepository.save(record);
        // 一问一答两条消息，刷新会话统计与更新时间
        conversationService.touch(conversationId, 2);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("passed", passed);
        result.put("score", score);
        result.put("total", total);
        result.put("state", state);
        result.put("feedback", feedback);
        result.put("answer", answer);
        result.put("sources", sources);
        result.put("knowledgeCovered", knowledgeCovered);
        result.put("gate", gate);
        result.put("teaching", teaching);
        result.put("mode", mode);
        result.put("model", model);
        result.put("modelSource", modelSource);
        result.put("recordId", record.getId());
        result.put("conversationId", conversationId);
        return result;
    }

    private boolean isSupportedImage(MultipartFile file) {
        String contentType = file.getContentType() == null ? "" : file.getContentType().toLowerCase(Locale.ROOT);
        if (VISION_CONTENT_TYPES.contains(contentType)) {
            return true;
        }
        if (!contentType.isBlank() && !"application/octet-stream".equals(contentType)) {
            return false;
        }
        String filename = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase(Locale.ROOT);
        for (String extension : VISION_EXTENSIONS) {
            if (filename.endsWith(extension)) {
                return true;
            }
        }
        return false;
    }

    private List<Object> toObjectList(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        if (value == null || value.isNull()) {
            return new ArrayList<>();
        }
        List<Object> parsed = jsonHelper.toList(jsonHelper.mapper().convertValue(value, Object.class));
        return parsed == null ? new ArrayList<>() : parsed;
    }

    private Object toObject(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value == null || value.isNull() ? null : jsonHelper.mapper().convertValue(value, Object.class);
    }

    private List<String> gatePrerequisites(Object gate, String key) {
        List<String> result = new ArrayList<>();
        if (gate == null) {
            return result;
        }
        Object prerequisites = jsonHelper.toMap(gate).get("prerequisites");
        if (!(prerequisites instanceof List<?> list)) {
            return result;
        }
        for (Object item : list) {
            Object value = jsonHelper.toMap(item).get(key);
            if (value != null && !String.valueOf(value).isBlank()) {
                result.add(String.valueOf(value));
            }
        }
        return result;
    }

    /** conversationId 兼容 JSON 数字与字符串；空值表示新建会话。 */
    private Long parseConversationId(Object raw) {
        if (raw == null) {
            return null;
        }
        if (raw instanceof Number number) {
            return number.longValue();
        }
        String text = String.valueOf(raw).trim();
        if (text.isEmpty() || "null".equalsIgnoreCase(text)) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "conversationId 参数格式错误");
        }
    }
}
