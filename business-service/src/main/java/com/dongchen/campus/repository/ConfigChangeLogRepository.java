package com.dongchen.campus.repository;

import com.dongchen.campus.domain.ConfigChangeLog;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ConfigChangeLogRepository extends JpaRepository<ConfigChangeLog, Long> {

    List<ConfigChangeLog> findByClassIdOrderByChangedAtDesc(String classId);
}
