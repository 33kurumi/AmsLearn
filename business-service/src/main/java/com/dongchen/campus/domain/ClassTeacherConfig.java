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
 * 班级教师配置（回答规则、难度、知识范围、知识库权限、禁用内容）。
 */
@Entity
@Table(name = "class_teacher_config")
@Getter
@Setter
@NoArgsConstructor
public class ClassTeacherConfig {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "class_id", nullable = false, unique = true, length = 50)
    private String classId;

    @Enumerated(EnumType.STRING)
    @Column(name = "answer_mode", nullable = false, length = 20)
    private AnswerMode answerMode;

    @Column(name = "max_difficulty", nullable = false)
    private Integer maxDifficulty;

    @Lob
    @Column(name = "knowledge_scope")
    private String knowledgeScope;

    @Column(name = "boundary_rules", length = 500)
    private String boundaryRules;

    @Lob
    @Column(name = "kb_access")
    private String kbAccess;

    @Lob
    @Column(name = "disabled_topics")
    private String disabledTopics;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @Column(name = "updated_by")
    private Long updatedBy;
}
