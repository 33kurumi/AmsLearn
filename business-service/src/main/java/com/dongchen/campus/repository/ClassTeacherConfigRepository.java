package com.dongchen.campus.repository;

import com.dongchen.campus.domain.ClassTeacherConfig;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ClassTeacherConfigRepository extends JpaRepository<ClassTeacherConfig, Long> {

    Optional<ClassTeacherConfig> findByClassId(String classId);
}
