package com.dongchen.campus.repository;

import com.dongchen.campus.domain.Report;
import com.dongchen.campus.domain.ReportType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface ReportRepository extends JpaRepository<Report, Long> {

    List<Report> findByStudentIdOrderByCreatedAtDesc(Long studentId);

    List<Report> findByStudentIdAndTypeOrderByCreatedAtDesc(Long studentId, ReportType type);

    Optional<Report> findFirstByStudentIdAndTypeOrderByCreatedAtDesc(Long studentId, ReportType type);

    Optional<Report> findByIdAndStudentId(Long id, Long studentId);

    List<Report> findByClassIdAndTypeAndCreatedAtGreaterThanEqual(
            String classId, ReportType type, LocalDateTime from);
}
