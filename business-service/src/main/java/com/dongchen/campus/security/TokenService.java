package com.dongchen.campus.security;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.config.AuthProperties;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.Base64;

/**
 * HMAC-SHA256 令牌：payload = userId:role:expEpoch，token = base64url(payload).base64url(signature)。
 */
@Component
public class TokenService {

    public record Payload(long userId, String role, long expiresAtEpoch) {
    }

    public record IssuedToken(String token, LocalDateTime expiresAt) {
    }

    private static final String HMAC_ALGORITHM = "HmacSHA256";

    private final byte[] secret;
    private final long ttlHours;
    private final Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
    private final Base64.Decoder decoder = Base64.getUrlDecoder();

    public TokenService(AuthProperties authProperties) {
        this.secret = authProperties.getTokenSecret().getBytes(StandardCharsets.UTF_8);
        this.ttlHours = authProperties.getTokenTtlHours() <= 0 ? 168 : authProperties.getTokenTtlHours();
    }

    public IssuedToken issue(long userId, String role) {
        long expiresAtEpoch = Instant.now().plus(ttlHours, ChronoUnit.HOURS).getEpochSecond();
        String payload = userId + ":" + role + ":" + expiresAtEpoch;
        String token = encoder.encodeToString(payload.getBytes(StandardCharsets.UTF_8))
                + "." + encoder.encodeToString(sign(payload));
        return new IssuedToken(token, LocalDateTime.now().plusHours(ttlHours).withNano(0));
    }

    public Payload verify(String token) {
        try {
            int dot = token.lastIndexOf('.');
            if (dot <= 0 || dot == token.length() - 1) {
                throw unauthorized();
            }
            String payload = new String(decoder.decode(token.substring(0, dot)), StandardCharsets.UTF_8);
            byte[] signature = decoder.decode(token.substring(dot + 1));
            if (!MessageDigest.isEqual(sign(payload), signature)) {
                throw unauthorized();
            }
            String[] parts = payload.split(":");
            if (parts.length != 3) {
                throw unauthorized();
            }
            long userId = Long.parseLong(parts[0]);
            long expiresAtEpoch = Long.parseLong(parts[2]);
            if (expiresAtEpoch < Instant.now().getEpochSecond()) {
                throw new BusinessException(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录");
            }
            return new Payload(userId, parts[1], expiresAtEpoch);
        } catch (BusinessException ex) {
            throw ex;
        } catch (RuntimeException ex) {
            throw unauthorized();
        }
    }

    private BusinessException unauthorized() {
        return new BusinessException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录");
    }

    private byte[] sign(String payload) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(secret, HMAC_ALGORITHM));
            return mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("令牌签名计算失败", ex);
        }
    }
}
