package com.dongchen.campus.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * 用户信息（师生账号）。
 */
@Entity
@Table(name = "user_info")
@Getter
@Setter
@NoArgsConstructor
public class UserInfo {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "username", nullable = false, unique = true, length = 50)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 200)
    private String passwordHash;

    @Column(name = "display_name", length = 50)
    private String displayName;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 20)
    private Role role;

    @Column(name = "class_id", length = 50)
    private String classId;

    @Column(name = "email", length = 100)
    private String email;

    @Column(name = "phone", length = 30)
    private String phone;

    @Column(name = "target_school", length = 100)
    private String targetSchool;

    @Column(name = "exam_year")
    private Integer examYear;

    // v1.2 用户 AI 配置：API Key 只存 AES/GCM 密文，接口只回掩码
    @Column(name = "ai_api_key_enc", length = 512)
    private String aiApiKeyEnc;

    @Column(name = "ai_base_url", length = 200)
    private String aiBaseUrl;

    @Column(name = "ai_model", length = 100)
    private String aiModel;

    @Column(name = "ai_enabled", nullable = false)
    private boolean aiEnabled;

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
