package com.dongchen.campus.seed;

import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.domain.KnowledgePoint;
import com.dongchen.campus.repository.KnowledgePointRepository;
import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * 知识点目录种子：读取 classpath:data/knowledge_points.json，空表时导入 67 条。
 */
@Component
@Order(1)
public class KnowledgePointSeeder implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(KnowledgePointSeeder.class);
    private static final String RESOURCE = "data/knowledge_points.json";

    private final KnowledgePointRepository knowledgePointRepository;
    private final JsonHelper jsonHelper;

    public KnowledgePointSeeder(KnowledgePointRepository knowledgePointRepository, JsonHelper jsonHelper) {
        this.knowledgePointRepository = knowledgePointRepository;
        this.jsonHelper = jsonHelper;
    }

    @Override
    public void run(String... args) throws Exception {
        long existing = knowledgePointRepository.count();
        if (existing > 0) {
            log.info("知识点目录已存在 {} 条，跳过导入", existing);
            return;
        }
        ClassPathResource resource = new ClassPathResource(RESOURCE);
        if (!resource.exists()) {
            log.warn("未找到知识点种子文件 {}，跳过导入", RESOURCE);
            return;
        }
        JsonNode root;
        try (InputStream in = resource.getInputStream()) {
            root = jsonHelper.mapper().readTree(in);
        }
        if (root == null || !root.isArray()) {
            log.warn("知识点种子文件格式不正确，跳过导入");
            return;
        }
        List<KnowledgePoint> points = new ArrayList<>();
        int index = 0;
        for (JsonNode node : root) {
            index++;
            KnowledgePoint point = new KnowledgePoint();
            point.setKpId(text(node, "kpId"));
            point.setKpName(text(node, "kpName"));
            point.setChapter(text(node, "chapter"));
            point.setDifficulty(number(node, "difficulty"));
            point.setHours(number(node, "hours"));
            point.setObjectives(text(node, "objectives"));
            point.setKeyPoints(text(node, "keyPoints"));
            point.setOrderIndex(index);
            points.add(point);
        }
        knowledgePointRepository.saveAll(points);
        log.info("知识点目录导入完成：{} 条", points.size());
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() ? null : value.asText();
    }

    private Integer number(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() || !value.isNumber() ? null : value.asInt();
    }
}
