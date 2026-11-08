package com.dongchen.campus.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 知识点目录（67 个）。
 */
@Entity
@Table(name = "knowledge_point")
@Getter
@Setter
@NoArgsConstructor
public class KnowledgePoint {

    @Id
    @Column(name = "kp_id", length = 20)
    private String kpId;

    @Column(name = "kp_name", length = 100)
    private String kpName;

    @Column(name = "chapter", length = 100)
    private String chapter;

    @Column(name = "difficulty")
    private Integer difficulty;

    @Column(name = "hours")
    private Integer hours;

    @Lob
    @Column(name = "objectives")
    private String objectives;

    @Lob
    @Column(name = "key_points")
    private String keyPoints;

    @Column(name = "order_index")
    private Integer orderIndex;
}
