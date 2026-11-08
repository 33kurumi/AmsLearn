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
 * 班级配置变更留痕。
 */
@Entity
@Table(name = "config_change_log")
@Getter
@Setter
@NoArgsConstructor
public class ConfigChangeLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "class_id", nullable = false, length = 50)
    private String classId;

    @Column(name = "changed_by")
    private Long changedBy;

    @Column(name = "changed_by_name", length = 50)
    private String changedByName;

    @Column(name = "summary", length = 500)
    private String summary;

    @Lob
    @Column(name = "changes")
    private String changes;

    @Column(name = "changed_at")
    private LocalDateTime changedAt;
}
