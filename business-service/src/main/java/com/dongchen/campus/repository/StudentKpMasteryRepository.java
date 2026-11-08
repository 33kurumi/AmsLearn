package com.dongchen.campus.repository;

import com.dongchen.campus.domain.StudentKpMastery;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface StudentKpMasteryRepository extends JpaRepository<StudentKpMastery, Long> {

    List<StudentKpMastery> findByStudentId(Long studentId);

    List<StudentKpMastery> findByStudentIdIn(Collection<Long> studentIds);

    Optional<StudentKpMastery> findByStudentIdAndKpId(Long studentId, String kpId);

    long countByStudentIdAndMasteryLessThan(Long studentId, double mastery);
}
