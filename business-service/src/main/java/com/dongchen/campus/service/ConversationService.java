package com.dongchen.campus.service;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.common.PageResult;
import com.dongchen.campus.domain.Conversation;
import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.RecordType;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.ConversationRepository;
import com.dongchen.campus.repository.InteractionRecordRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 答疑会话（v1.2）：会话 CRUD 与历史消息组装，消息本体仍存 interaction_record。
 */
@Service
public class ConversationService {

    private static final String DEFAULT_TITLE = "新对话";
    private static final int TITLE_MAX_LENGTH = 100;
    private static final int MAX_HISTORY_MESSAGES = 6;

    private final AuthService authService;
    private final ConversationRepository conversationRepository;
    private final InteractionRecordRepository interactionRepository;
    private final JsonHelper jsonHelper;

    public ConversationService(AuthService authService, ConversationRepository conversationRepository,
                               InteractionRecordRepository interactionRepository, JsonHelper jsonHelper) {
        this.authService = authService;
        this.conversationRepository = conversationRepository;
        this.interactionRepository = interactionRepository;
        this.jsonHelper = jsonHelper;
    }

    @Transactional
    public Map<String, Object> create(String title) {
        UserInfo user = authService.currentUser();
        String normalized = normalizeTitle(title, true);
        LocalDateTime now = LocalDateTime.now();
        Conversation conversation = new Conversation();
        conversation.setStudentId(user.getId());
        conversation.setClassId(user.getClassId());
        conversation.setTitle(normalized);
        conversation.setMessageCount(0);
        conversation.setCreatedAt(now);
        conversation.setUpdatedAt(now);
        conversationRepository.save(conversation);
        return Maps.of(
                "id", conversation.getId(),
                "title", conversation.getTitle(),
                "createdAt", conversation.getCreatedAt());
    }

    public PageResult<Map<String, Object>> list(Integer page, Integer size) {
        UserInfo user = authService.currentUser();
        List<Map<String, Object>> items = new ArrayList<>();
        for (Conversation conversation : conversationRepository.findByStudentIdOrderByUpdatedAtDesc(user.getId())) {
            items.add(listVo(conversation));
        }
        return PageResult.of(items, page, size);
    }

    public Map<String, Object> detail(Long id) {
        Conversation conversation = requireOwned(id);
        List<Map<String, Object>> messages = new ArrayList<>();
        for (InteractionRecord record : interactionRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId())) {
            Map<String, Object> userMessage = new LinkedHashMap<>();
            userMessage.put("recordId", record.getId());
            userMessage.put("role", "user");
            userMessage.put("content", record.getUserMessage());
            userMessage.put("sources", List.of());
            userMessage.put("blocked", false);
            userMessage.put("blockReason", null);
            userMessage.put("knowledgeCovered", true);
            userMessage.put("scopeWarning", null);
            userMessage.put("createdAt", record.getCreatedAt());
            messages.add(userMessage);

            Map<String, Object> assistantMessage = new LinkedHashMap<>();
            assistantMessage.put("recordId", record.getId());
            assistantMessage.put("role", "assistant");
            assistantMessage.put("content", record.getAiResponse());
            assistantMessage.put("sources", jsonHelper.readList(record.getSources()));
            assistantMessage.put("blocked", record.isBlocked());
            assistantMessage.put("blockReason", record.getBlockReason());
            assistantMessage.put("knowledgeCovered", record.isKnowledgeCovered());
            assistantMessage.put("scopeWarning", record.getScopeWarning());
            // v1.3：gate 状态（无则 null），供前端历史会话只读展示前置测试结果
            assistantMessage.put("gate", readGate(record.getGateJson()));
            assistantMessage.put("createdAt", record.getCreatedAt());
            messages.add(assistantMessage);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", conversation.getId());
        result.put("title", conversation.getTitle());
        result.put("createdAt", conversation.getCreatedAt());
        result.put("messages", messages);
        return result;
    }

    private Object readGate(String gateJson) {
        if (gateJson == null || gateJson.isBlank()) {
            return null;
        }
        return jsonHelper.readMap(gateJson);
    }

    @Transactional
    public Map<String, Object> rename(Long id, String title) {
        Conversation conversation = requireOwned(id);
        conversation.setTitle(normalizeTitle(title, false));
        conversation.setUpdatedAt(LocalDateTime.now());
        conversationRepository.save(conversation);
        return Maps.of(
                "id", conversation.getId(),
                "title", conversation.getTitle(),
                "createdAt", conversation.getCreatedAt());
    }

    @Transactional
    public void delete(Long id) {
        Conversation conversation = requireOwned(id);
        // 学习记录保留（学习痕迹不因删会话丢失），仅解除会话归属
        for (InteractionRecord record : interactionRepository.findByConversationIdOrderByCreatedAtAsc(id)) {
            record.setConversationId(null);
            interactionRepository.save(record);
        }
        conversationRepository.delete(conversation);
    }

    /** /api/chat 使用：会话不存在 404，非本人 403。 */
    public Conversation requireOwned(Long id) {
        UserInfo user = authService.currentUser();
        Conversation conversation = conversationRepository.findById(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "会话不存在"));
        if (!user.getId().equals(conversation.getStudentId())) {
            throw new BusinessException(ErrorCode.FORBIDDEN, "无权访问该会话");
        }
        return conversation;
    }

    /** 该会话最近 6 条消息（user/assistant 交替，时间正序），用于 /api/chat 的 history。 */
    public List<Map<String, Object>> history(Long conversationId) {
        if (conversationId == null) {
            return List.of();
        }
        List<InteractionRecord> records =
                interactionRepository.findByConversationIdOrderByCreatedAtAsc(conversationId);
        List<Map<String, Object>> messages = new ArrayList<>();
        for (InteractionRecord record : records) {
            messages.add(Maps.of("role", "user", "content", record.getUserMessage()));
            messages.add(Maps.of("role", "assistant", "content", record.getAiResponse()));
        }
        if (messages.size() <= MAX_HISTORY_MESSAGES) {
            return messages;
        }
        return new ArrayList<>(messages.subList(messages.size() - MAX_HISTORY_MESSAGES, messages.size()));
    }

    /** 新建会话标题：消息前 20 字。 */
    public static String titleFromMessage(String message) {
        String text = message == null ? "" : message.trim().replaceAll("\\s+", " ");
        if (text.isEmpty()) {
            return DEFAULT_TITLE;
        }
        return text.length() <= 20 ? text : text.substring(0, 20);
    }

    private Map<String, Object> listVo(Conversation conversation) {
        List<InteractionRecord> records =
                interactionRepository.findByConversationIdOrderByCreatedAtAsc(conversation.getId());
        String lastMessage = records.isEmpty() ? null : records.get(records.size() - 1).getUserMessage();
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("id", conversation.getId());
        vo.put("title", conversation.getTitle());
        vo.put("messageCount", conversation.getMessageCount());
        vo.put("lastMessage", lastMessage);
        vo.put("updatedAt", conversation.getUpdatedAt());
        return vo;
    }

    @Transactional
    public Conversation createForChat(UserInfo user, String message) {
        LocalDateTime now = LocalDateTime.now();
        Conversation conversation = new Conversation();
        conversation.setStudentId(user.getId());
        conversation.setClassId(user.getClassId());
        conversation.setTitle(titleFromMessage(message));
        conversation.setMessageCount(0);
        conversation.setCreatedAt(now);
        conversation.setUpdatedAt(now);
        return conversationRepository.save(conversation);
    }

    private String normalizeTitle(String title, boolean defaultWhenBlank) {
        if (title == null) {
            if (defaultWhenBlank) {
                return DEFAULT_TITLE;
            }
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "会话标题不能为空");
        }
        String trimmed = title.trim();
        if (trimmed.isEmpty()) {
            if (defaultWhenBlank) {
                return DEFAULT_TITLE;
            }
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "会话标题不能为空");
        }
        if (trimmed.length() > TITLE_MAX_LENGTH) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "会话标题不能超过 100 个字符");
        }
        return trimmed;
    }

    /** 供 ChatService 落库后刷新会话统计。 */
    @Transactional
    public void touch(Long conversationId, int addedMessages) {
        Conversation conversation = conversationRepository.findById(conversationId).orElse(null);
        if (conversation == null) {
            return;
        }
        conversation.setMessageCount(conversation.getMessageCount() + addedMessages);
        conversation.setUpdatedAt(LocalDateTime.now());
        conversationRepository.save(conversation);
    }
}
