package com.dongchen.campus.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 敏感字段加密配置：AES/GCM 密钥来自 app.crypto.secret，默认值为开发用密钥。
 */
@ConfigurationProperties(prefix = "app.crypto")
public class CryptoProperties {

    private String secret = "AmsLearn-Demo-AES-Secret-2026-ChangeMe";

    public String getSecret() {
        return secret;
    }

    public void setSecret(String secret) {
        this.secret = secret;
    }
}
