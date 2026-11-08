package com.dongchen.campus.service;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.config.AppProperties;
import com.dongchen.campus.domain.ClassInfo;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.domain.Role;
import com.dongchen.campus.domain.StudentKpMastery;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.ClassInfoRepository;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.dongchen.campus.repository.StudentKpMasteryRepository;
import com.dongchen.campus.repository.UserRepository;
import com.dongchen.campus.security.CurrentUser;
import com.dongchen.campus.security.PasswordHasher;
import com.dongchen.campus.security.TokenService;
import com.dongchen.campus.security.UserContext;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordHasher passwordHasher;
    private final TokenService tokenService;
    private final UserMapper userMapper;
    private final ClassInfoRepository classInfoRepository;
    private final KnowledgePointRepository knowledgePointRepository;
    private final StudentKpMasteryRepository masteryRepository;
    private final AppProperties appProperties;

    public AuthService(UserRepository userRepository, PasswordHasher passwordHasher,
                       TokenService tokenService, UserMapper userMapper,
                       ClassInfoRepository classInfoRepository,
                       KnowledgePointRepository knowledgePointRepository,
                       StudentKpMasteryRepository masteryRepository,
                       AppProperties appProperties) {
        this.userRepository = userRepository;
        this.passwordHasher = passwordHasher;
        this.tokenService = tokenService;
        this.userMapper = userMapper;
        this.classInfoRepository = classInfoRepository;
        this.knowledgePointRepository = knowledgePointRepository;
        this.masteryRepository = masteryRepository;
        this.appProperties = appProperties;
    }

    public Map<String, Object> login(String username, String password) {
        UserInfo user = userRepository.findByUsername(username)
                .orElseThrow(() -> new BusinessException(ErrorCode.UNAUTHORIZED, "用户名或密码错误"));
        if (!passwordHasher.matches(password, user.getPasswordHash())) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED, "用户名或密码错误");
        }
        return issueLoginResult(user);
    }

    /**
     * v1.4 学生注册即登录：创建 STUDENT 用户、初始化 67 条知识点掌握度，并签发令牌。
     */
    @Transactional
    public Map<String, Object> register(String username, String password, String displayName, String email) {
        String name = username == null ? "" : username.trim();
        if (!name.matches("^[A-Za-z0-9_]{4,20}$")) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "username 用户名应为 4~20 位字母、数字或下划线");
        }
        if (password == null || password.length() < 6 || password.length() > 32) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "password 密码长度应为 6~32 位");
        }
        String nick = displayName == null ? "" : displayName.trim();
        if (nick.isEmpty() || nick.length() > 20) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "displayName 昵称长度应为 1~20 个字符");
        }
        if (userRepository.findByUsername(name).isPresent()) {
            throw new BusinessException(ErrorCode.CONFLICT, "用户名已存在，请更换");
        }

        UserInfo user = new UserInfo();
        user.setUsername(name);
        user.setPasswordHash(passwordHasher.hash(password));
        user.setDisplayName(nick);
        user.setRole(Role.STUDENT);
        user.setClassId(resolveDefaultClassId());
        user.setEmail(email == null || email.isBlank() ? null : email.trim());
        user.setCreatedAt(LocalDateTime.now());
        try {
            userRepository.saveAndFlush(user);
        } catch (DataIntegrityViolationException ex) {
            throw new BusinessException(ErrorCode.CONFLICT, "用户名已存在，请更换");
        }

        initMastery(user.getId());
        return issueLoginResult(user);
    }

    public Map<String, Object> me() {
        return userMapper.toVo(currentUser());
    }

    public UserInfo currentUser() {
        CurrentUser current = UserContext.require();
        return userRepository.findById(current.userId())
                .orElseThrow(() -> new BusinessException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录"));
    }

    @Transactional
    public void changePassword(String oldPassword, String newPassword) {
        if (newPassword == null || newPassword.length() < 6) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "新密码长度不能少于 6 位");
        }
        UserInfo user = currentUser();
        if (!passwordHasher.matches(oldPassword, user.getPasswordHash())) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "原密码不正确");
        }
        user.setPasswordHash(passwordHasher.hash(newPassword));
        userRepository.save(user);
    }

    @Transactional
    public Map<String, Object> updateProfile(String displayName, String email, String phone,
                                             String targetSchool, Integer examYear) {
        UserInfo user = currentUser();
        if (displayName != null) {
            if (displayName.isBlank()) {
                throw new BusinessException(ErrorCode.VALIDATION_ERROR, "昵称不能为空");
            }
            user.setDisplayName(displayName.trim());
        }
        if (email != null) {
            user.setEmail(email.trim());
        }
        if (phone != null) {
            user.setPhone(phone.trim());
        }
        if (targetSchool != null) {
            user.setTargetSchool(targetSchool.trim());
        }
        if (examYear != null) {
            user.setExamYear(examYear);
        }
        userRepository.save(user);
        return userMapper.toVo(user);
    }

    private Map<String, Object> issueLoginResult(UserInfo user) {
        TokenService.IssuedToken token = tokenService.issue(user.getId(), user.getRole().name());
        Map<String, Object> result = Maps.of();
        result.put("token", token.token());
        result.put("expiresAt", token.expiresAt());
        result.put("user", userMapper.toVo(user));
        return result;
    }

    /** app.default-class-id 指向的班级，不存在时回退到库中第一个班级。 */
    private String resolveDefaultClassId() {
        String configured = appProperties.getDefaultClassId();
        if (configured != null && !configured.isBlank()) {
            ClassInfo info = classInfoRepository.findById(configured).orElse(null);
            if (info != null) {
                return info.getClassId();
            }
        }
        return classInfoRepository.findAll().stream()
                .findFirst()
                .map(ClassInfo::getClassId)
                .orElse(null);
    }

    /** 新用户为全部知识点初始化掌握度（mastery/attempts/correctCount 均为 0）。 */
    private void initMastery(Long studentId) {
        List<KnowledgePoint> points = knowledgePointRepository.findAllByOrderByOrderIndexAsc();
        if (points.isEmpty()) {
            return;
        }
        LocalDateTime now = LocalDateTime.now();
        List<StudentKpMastery> rows = new ArrayList<>(points.size());
        for (KnowledgePoint point : points) {
            StudentKpMastery row = new StudentKpMastery();
            row.setStudentId(studentId);
            row.setKpId(point.getKpId());
            row.setMastery(0.0);
            row.setAttempts(0);
            row.setCorrectCount(0);
            row.setUpdatedAt(now);
            rows.add(row);
        }
        masteryRepository.saveAll(rows);
    }
}
