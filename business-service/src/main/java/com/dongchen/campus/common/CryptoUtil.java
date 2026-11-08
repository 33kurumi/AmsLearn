package com.dongchen.campus.common;

import com.dongchen.campus.config.CryptoProperties;
import org.springframework.stereotype.Component;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * AES/GCM 敏感字段加解密（v1.2 用户 AI Key）。
 * 存储格式：gcm:base64url(iv).base64url(cipherText)，密钥由 app.crypto.secret 经 SHA-256 派生 32 字节。
 */
@Component
public class CryptoUtil {

    private static final String PREFIX = "gcm:";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private final SecretKeySpec key;
    private final Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
    private final Base64.Decoder decoder = Base64.getUrlDecoder();

    public CryptoUtil(CryptoProperties properties) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(properties.getSecret().getBytes(StandardCharsets.UTF_8));
            this.key = new SecretKeySpec(digest, "AES");
        } catch (Exception ex) {
            throw new IllegalStateException("初始化加密密钥失败", ex);
        }
    }

    public String encrypt(String plainText) {
        if (plainText == null || plainText.isEmpty()) {
            return null;
        }
        try {
            byte[] iv = new byte[IV_BYTES];
            RANDOM.nextBytes(iv);
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            byte[] encrypted = cipher.doFinal(plainText.getBytes(StandardCharsets.UTF_8));
            return PREFIX + encoder.encodeToString(iv) + "." + encoder.encodeToString(encrypted);
        } catch (Exception ex) {
            throw new IllegalStateException("敏感数据加密失败", ex);
        }
    }

    public String decrypt(String stored) {
        if (stored == null || stored.isBlank()) {
            return null;
        }
        try {
            String payload = stored.startsWith(PREFIX) ? stored.substring(PREFIX.length()) : stored;
            int dot = payload.indexOf('.');
            if (dot <= 0) {
                throw new IllegalArgumentException("密文格式错误");
            }
            byte[] iv = decoder.decode(payload.substring(0, dot));
            byte[] encrypted = decoder.decode(payload.substring(dot + 1));
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception ex) {
            throw new IllegalStateException("敏感数据解密失败", ex);
        }
    }

    /** 接口展示用掩码：sk-1234567890abcd -> sk-***abcd。 */
    public static String mask(String rawKey) {
        if (rawKey == null || rawKey.isBlank()) {
            return null;
        }
        String key = rawKey.trim();
        if (key.length() <= 8) {
            return "***";
        }
        return key.substring(0, 3) + "***" + key.substring(key.length() - 4);
    }
}
