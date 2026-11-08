package com.dongchen.campus.service;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.CryptoUtil;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.domain.UserInfo;
import com.dongchen.campus.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

/**
 * 个人 AI 配置（v1.2）：API Key 加密落库，接口只返回掩码。
 */
@Service
public class ProfileAiService {

    private static final String DEFAULT_BASE_URL = "https://api.deepseek.com";
    private static final String DEFAULT_MODEL = "deepseek-flash";

    private final AuthService authService;
    private final UserRepository userRepository;
    private final CryptoUtil cryptoUtil;

    public ProfileAiService(AuthService authService, UserRepository userRepository, CryptoUtil cryptoUtil) {
        this.authService = authService;
        this.userRepository = userRepository;
        this.cryptoUtil = cryptoUtil;
    }

    public Map<String, Object> get() {
        return toVo(authService.currentUser());
    }

    @Transactional
    public Map<String, Object> update(String apiKey, String baseUrl, String model, Boolean enabled) {
        UserInfo user = authService.currentUser();
        if (apiKey != null) {
            String trimmed = apiKey.trim();
            user.setAiApiKeyEnc(trimmed.isEmpty() ? null : cryptoUtil.encrypt(trimmed));
        }
        if (baseUrl != null) {
            String trimmed = baseUrl.trim();
            if (trimmed.isEmpty()) {
                user.setAiBaseUrl(null);
            } else {
                if (!trimmed.toLowerCase().startsWith("https://")) {
                    throw new BusinessException(ErrorCode.VALIDATION_ERROR, "Base URL 必须以 https:// 开头");
                }
                user.setAiBaseUrl(trimmed);
            }
        }
        if (model != null) {
            String trimmed = model.trim();
            if (trimmed.isEmpty()) {
                throw new BusinessException(ErrorCode.VALIDATION_ERROR, "模型名称不能为空");
            }
            user.setAiModel(trimmed);
        }
        if (enabled != null) {
            user.setAiEnabled(enabled);
        }
        userRepository.save(user);
        return toVo(user);
    }

    @Transactional
    public Map<String, Object> clear() {
        UserInfo user = authService.currentUser();
        user.setAiApiKeyEnc(null);
        user.setAiBaseUrl(null);
        user.setAiModel(null);
        user.setAiEnabled(false);
        userRepository.save(user);
        return toVo(user);
    }

    /**
     * 当前用户启用了自己的 Key 时返回解密后的 llm 覆盖参数，否则返回 null。
     */
    public Map<String, Object> effectiveLlm(UserInfo user) {
        if (user == null || !user.isAiEnabled()) {
            return null;
        }
        String enc = user.getAiApiKeyEnc();
        if (enc == null || enc.isBlank()) {
            return null;
        }
        String apiKey;
        try {
            apiKey = cryptoUtil.decrypt(enc);
        } catch (RuntimeException ex) {
            return null;
        }
        if (apiKey == null || apiKey.isBlank()) {
            return null;
        }
        return Maps.of(
                "apiKey", apiKey,
                "baseUrl", user.getAiBaseUrl() == null ? DEFAULT_BASE_URL : user.getAiBaseUrl(),
                "model", user.getAiModel() == null ? DEFAULT_MODEL : user.getAiModel());
    }

    private Map<String, Object> toVo(UserInfo user) {
        String masked = null;
        if (user.getAiApiKeyEnc() != null && !user.getAiApiKeyEnc().isBlank()) {
            try {
                masked = CryptoUtil.mask(cryptoUtil.decrypt(user.getAiApiKeyEnc()));
            } catch (RuntimeException ex) {
                masked = "***";
            }
        }
        return Maps.of(
                "enabled", user.isAiEnabled(),
                "baseUrl", user.getAiBaseUrl(),
                "model", user.getAiModel(),
                "hasApiKey", masked != null,
                "apiKeyMasked", masked);
    }
}
