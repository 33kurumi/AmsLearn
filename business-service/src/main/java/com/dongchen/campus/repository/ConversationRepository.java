package com.dongchen.campus.repository;

import com.dongchen.campus.domain.Conversation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ConversationRepository extends JpaRepository<Conversation, Long> {

    List<Conversation> findByStudentIdOrderByUpdatedAtDesc(Long studentId);

    Optional<Conversation> findByIdAndStudentId(Long id, Long studentId);

    long countByStudentId(Long studentId);
}
