package com.dongchen.campus.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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
 * 错题记录。
 */
@Entity
@Table(name = "wrong_question")
@Getter
@Setter
@NoArgsConstructor
public class WrongQuestion {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "student_id", nullable = false)
    private Long studentId;

    @Column(name = "class_id", length = 50)
    private String classId;

    @Column(name = "kp_id", length = 20)
    private String kpId;

    @Column(name = "kp_name", length = 100)
    private String kpName;

    @Lob
    @Column(name = "question_text")
    private String questionText;

    @Column(name = "question_type", length = 20)
    private String questionType;

    @Column(name = "difficulty")
    private Integer difficulty;

    @Column(name = "student_answer", length = 500)
    private String studentAnswer;

    @Column(name = "correct_answer", length = 500)
    private String correctAnswer;

    @Column(name = "error_type", length = 30)
    private String errorType;

    @Lob
    @Column(name = "analysis")
    private String analysis;

    @Column(name = "source_type", length = 30)
    private String sourceType;

    @Column(name = "reviewed", nullable = false)
    private boolean reviewed;

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
