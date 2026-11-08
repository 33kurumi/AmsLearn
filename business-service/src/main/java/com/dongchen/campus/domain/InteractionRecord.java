package com.dongchen.campus.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 交互答题记录：所有学生端交互均落库留痕。
 */
@Entity
@Table(name = "interaction_record")
@Getter
@Setter
@NoArgsConstructor
public class InteractionRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "student_id", nullable = false)
    private Long studentId;

    @Column(name = "class_id", length = 50)
    private String classId;

    @Enumerated(EnumType.STRING)
    @Column(name = "record_type", nullable = false, length = 20)
    private RecordType type;

    @Column(name = "intent", length = 20)
    private String intent;

    @Lob
    @Column(name = "user_message")
    private String userMessage;

    @Lob
    @Column(name = "ai_response")
    private String aiResponse;

    @Lob
    @Column(name = "sources")
    private String sources;

    @Column(name = "kp_ids", length = 2000)
    private String kpIds;

    @Column(name = "kp_names", length = 2000)
    private String kpNames;

    @Column(name = "blocked", nullable = false)
    private boolean blocked;

    @Column(name = "block_reason", length = 500)
    private String blockReason;

    // v1.2：AI /qa 的覆盖标记与范围提示，供会话历史完整还原
    @Column(name = "knowledge_covered", nullable = false)
    private boolean knowledgeCovered = true;

    @Column(name = "scope_warning", length = 500)
    private String scopeWarning;

    // v1.2：所属会话，旧数据为 null
    @Column(name = "conversation_id")
    private Long conversationId;

    // v1.3：AI gate（前置自测）状态 JSON，无则为 null
    @Column(name = "gate_json", length = 8000)
    private String gateJson;

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
