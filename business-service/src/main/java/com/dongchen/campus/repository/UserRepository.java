package com.dongchen.campus.repository;

import com.dongchen.campus.domain.Role;
import com.dongchen.campus.domain.UserInfo;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface UserRepository extends JpaRepository<UserInfo, Long> {

    Optional<UserInfo> findByUsername(String username);

    List<UserInfo> findByClassIdAndRole(String classId, Role role);

    long countByClassIdAndRole(String classId, Role role);

    List<UserInfo> findByRole(Role role);
}
