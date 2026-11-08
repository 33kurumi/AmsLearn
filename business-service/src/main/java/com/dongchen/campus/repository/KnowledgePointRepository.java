package com.dongchen.campus.repository;

import com.dongchen.campus.domain.KnowledgePoint;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface KnowledgePointRepository extends JpaRepository<KnowledgePoint, String> {

    List<KnowledgePoint> findAllByOrderByOrderIndexAsc();
}
