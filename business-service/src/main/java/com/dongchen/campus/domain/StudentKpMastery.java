package com.dongchen.campus.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 学生知识点掌握度（student_id + kp_id 联合唯一）。
 */
@Entity
@Table(name = "student_kp_mastery", uniqueConstraints = @UniqueConstraint(columnNames = {"student_id", "kp_id"}))
@Getter
@Setter
@NoArgsConstructor
public class StudentKpMastery {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "student_id", nullable = false)
    private Long studentId;

    @Column(name = "kp_id", nullable = false, length = 20)
    private String kpId;

    @Column(name = "mastery", nullable = false)
    private double mastery;

    @Column(name = "attempts", nullable = false)
    private int attempts;

    @Column(name = "correct_count", nullable = false)
    private int correctCount;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
