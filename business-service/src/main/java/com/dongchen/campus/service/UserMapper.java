package com.dongchen.campus.service;

import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.ClassInfo;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.ClassInfoRepository;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * 用户与班级的对外视图转换。
 */
@Component
public class UserMapper {

    private final ClassInfoRepository classInfoRepository;

    public UserMapper(ClassInfoRepository classInfoRepository) {
        this.classInfoRepository = classInfoRepository;
    }

    public Map<String, Object> toVo(UserInfo user) {
        ClassInfo classInfo = user.getClassId() == null
                ? null
                : classInfoRepository.findById(user.getClassId()).orElse(null);
        return Maps.of(
                "id", user.getId(),
                "username", user.getUsername(),
                "displayName", user.getDisplayName(),
                "role", user.getRole() == null ? null : user.getRole().name(),
                "classId", user.getClassId(),
                "className", classInfo == null ? null : classInfo.getClassName(),
                "subject", classInfo == null ? null : classInfo.getSubject(),
                "email", user.getEmail(),
                "phone", user.getPhone(),
                "targetSchool", user.getTargetSchool(),
                "examYear", user.getExamYear());
    }

    public ClassInfo classInfo(String classId) {
        return classId == null ? null : classInfoRepository.findById(classId).orElse(null);
    }

    public Map<String, Object> classInfoVo(String classId) {
        ClassInfo info = classInfo(classId);
        if (info == null) {
            return Maps.of("classId", classId, "className", null, "subject", null, "teacherName", null);
        }
        return Maps.of(
                "classId", info.getClassId(),
                "className", info.getClassName(),
                "subject", info.getSubject(),
                "teacherName", info.getTeacherName());
    }
}
