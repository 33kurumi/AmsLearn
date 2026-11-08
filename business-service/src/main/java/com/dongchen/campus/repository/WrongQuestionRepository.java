package com.dongchen.campus.repository;

import com.dongchen.campus.domain.WrongQuestion;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

public interface WrongQuestionRepository extends JpaRepository<WrongQuestion, Long> {

    List<WrongQuestion> findByStudentIdOrderByCreatedAtDesc(Long studentId);

    List<WrongQuestion> findByStudentIdAndCreatedAtGreaterThanEqual(Long studentId, LocalDateTime from);

    List<WrongQuestion> findByClassIdAndCreatedAtGreaterThanEqual(String classId, LocalDateTime from);

    long countByStudentId(Long studentId);

    long countByStudentIdAndReviewedFalse(Long studentId);
}
