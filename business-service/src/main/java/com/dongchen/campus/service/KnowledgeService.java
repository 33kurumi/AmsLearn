package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.domain.Role;
import com.dongchen.campus.domain.UserInfo;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * T9 ~ T13 知识库管理：代理 AI 服务的知识库接口。
 */
@Service
public class KnowledgeService {

    private static final long MAX_FILE_SIZE = 2L * 1024 * 1024;
    private static final String DEFAULT_KB = "KB4";
    private static final List<String> ALLOWED_EXTENSIONS = List.of("md", "txt");

    private final AuthService authService;
    private final AiServiceClient aiServiceClient;
    private final JsonHelper jsonHelper;

    public KnowledgeService(AuthService authService, AiServiceClient aiServiceClient, JsonHelper jsonHelper) {
        this.authService = authService;
        this.aiServiceClient = aiServiceClient;
        this.jsonHelper = jsonHelper;
    }

    public Map<String, Object> documents() {
        UserInfo teacher = requireTeacher();
        JsonNode node = aiServiceClient.knowledgeDocuments(teacher.getClassId());
        return jsonHelper.toMap(node);
    }

    public Map<String, Object> upload(MultipartFile file, String kb) {
        UserInfo teacher = requireTeacher();
        if (file == null || file.isEmpty()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "上传文件不能为空");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "文件大小不能超过 2MB");
        }
        String filename = file.getOriginalFilename() == null ? "" : file.getOriginalFilename();
        int dot = filename.lastIndexOf('.');
        String extension = dot < 0 ? "" : filename.substring(dot + 1).toLowerCase(Locale.ROOT);
        if (!ALLOWED_EXTENSIONS.contains(extension)) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "仅支持 .md 或 .txt 文件");
        }
        String targetKb = kb == null || kb.isBlank() ? DEFAULT_KB : kb.trim().toUpperCase(Locale.ROOT);
        if (!targetKb.startsWith("KB")) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "知识库标识应为 KB1~KB4");
        }
        JsonNode node = aiServiceClient.knowledgeUpload(file, targetKb, teacher.getClassId(), teacher.getId());
        // 契约 T10 返回新 document；AI13 返回 {"document":{},"chunks":12}，这里取出 document 本体
        JsonNode document = node != null && node.has("document") && node.get("document").isObject()
                ? node.get("document") : node;
        return jsonHelper.toMap(document);
    }

    public Map<String, Object> toggle(String documentId, Boolean enabled) {
        UserInfo teacher = requireTeacher();
        if (enabled == null) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "enabled 不能为空");
        }
        JsonNode node = aiServiceClient.knowledgeToggle(documentId, enabled);
        // 契约 T11 返回 document 本体（AI14 已返回 document）
        JsonNode document = node != null && node.has("document") && node.get("document").isObject()
                ? node.get("document") : node;
        return jsonHelper.toMap(document);
    }

    public void delete(String documentId) {
        requireTeacher();
        aiServiceClient.knowledgeDelete(documentId);
    }

    public Map<String, Object> rebuild() {
        requireTeacher();
        JsonNode node = aiServiceClient.knowledgeRebuild();
        return jsonHelper.toMap(node);
    }

    private UserInfo requireTeacher() {
        UserInfo user = authService.currentUser();
        if (user.getRole() != Role.TEACHER) {
            throw new BusinessException(ErrorCode.FORBIDDEN, "仅教师可管理知识库");
        }
        if (user.getClassId() == null || user.getClassId().isBlank()) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "当前教师未绑定班级");
        }
        return user;
    }
}
