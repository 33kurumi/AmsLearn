package com.dongchen.campus.repository;

import com.dongchen.campus.domain.InteractionRecord;
import com.dongchen.campus.domain.RecordType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface InteractionRecordRepository extends JpaRepository<InteractionRecord, Long> {

    List<InteractionRecord> findByStudentIdOrderByCreatedAtDesc(Long studentId);

    List<InteractionRecord> findByClassIdOrderByCreatedAtDesc(String classId);

    List<InteractionRecord> findByClassIdAndCreatedAtGreaterThanEqualOrderByCreatedAtDesc(String classId, LocalDateTime from);

    List<InteractionRecord> findByClassIdAndTypeAndCreatedAtGreaterThanEqualOrderByCreatedAtDesc(
            String classId, RecordType type, LocalDateTime from);

    List<InteractionRecord> findByStudentIdAndTypeOrderByCreatedAtDesc(Long studentId, RecordType type);

    Optional<InteractionRecord> findFirstByStudentIdOrderByCreatedAtDesc(Long studentId);

    List<InteractionRecord> findByConversationIdOrderByCreatedAtAsc(Long conversationId);

    long countByConversationId(Long conversationId);

    long countByStudentId(Long studentId);

    long countByStudentIdAndType(Long studentId, RecordType type);

    long countByStudentIdAndCreatedAtGreaterThanEqual(Long studentId, LocalDateTime from);

    long countByClassId(String classId);

    long countByClassIdAndCreatedAtGreaterThanEqual(String classId, LocalDateTime from);
}
