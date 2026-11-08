package com.dongchen.campus.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private boolean demoData = true;

    /** v1.4 新注册学生默认加入的班级（不存在时回退到第一个班级）。 */
    private String defaultClassId = "C-GS-01";

    public boolean isDemoData() {
        return demoData;
    }

    public void setDemoData(boolean demoData) {
        this.demoData = demoData;
    }

    public String getDefaultClassId() {
        return defaultClassId;
    }

    public void setDefaultClassId(String defaultClassId) {
        this.defaultClassId = defaultClassId;
    }
}
