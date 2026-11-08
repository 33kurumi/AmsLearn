package com.dongchen.campus.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 班级信息。
 */
@Entity
@Table(name = "class_info")
@Getter
@Setter
@NoArgsConstructor
public class ClassInfo {

    @Id
    @Column(name = "class_id", length = 50)
    private String classId;

    @Column(name = "class_name", length = 100)
    private String className;

    @Column(name = "subject", length = 50)
    private String subject;

    @Column(name = "teacher_id")
    private Long teacherId;

    @Column(name = "teacher_name", length = 50)
    private String teacherName;
}
