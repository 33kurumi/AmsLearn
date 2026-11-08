package com.dongchen.campus.service;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.Maps;
import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
public class HealthService {

    private static final Logger log = LoggerFactory.getLogger(HealthService.class);

    private final AiServiceClient aiServiceClient;

    public HealthService(AiServiceClient aiServiceClient) {
        this.aiServiceClient = aiServiceClient;
    }

    public Map<String, Object> health() {
        Map<String, Object> result = new LinkedHashMap<>();
        String aiStatus = "DOWN";
        String mode = "unknown";
        int documents = 0;
        int chunks = 0;
        // v1.1 向量库可观测字段（AI /health 原始为 snake_case；AI 不可达时给空串/0，不抛错）
        String vectorStore = "";
        String embedding = "";
        int vectorDim = 0;
        int vectorCount = 0;
        // v1.2：AI 模式/模型来源与 embedding provider 可观测字段
        String model = "";
        String modelSource = "";
        String embeddingProvider = "";
        String embeddingModel = "";
        boolean supportsUserKey = true;
        // v1.3：识图能力（AI 未配置时 provider=none / ready=false）
        String visionProvider = "";
        String visionModel = "";
        boolean visionReady = false;
        try {
            JsonNode node = aiServiceClient.health();
            if (node != null) {
                aiStatus = text(node, "status", "UP");
                mode = text(node, "mode", "unknown");
                documents = integer(node, "knowledge_documents");
                chunks = integer(node, "knowledge_chunks");
                vectorStore = vectorStoreName(node);
                embedding = firstText(node, "embedding", "embedding_model", "embeddingModel", "embedding_name");
                vectorDim = firstInteger(node, "vector_dim", "vectorDim", "dimension");
                vectorCount = firstInteger(node, "vector_count", "vectorCount");
                model = firstText(node, "model", "llm_model");
                embeddingProvider = firstText(node, "embedding_provider", "embeddingProvider");
                embeddingModel = firstText(node, "embedding_model", "embeddingModel");
                modelSource = firstText(node, "modelSource", "model_source");
                supportsUserKey = !node.has("supports_user_key") || node.get("supports_user_key").asBoolean(true);
                visionProvider = firstText(node, "vision_provider", "visionProvider");
                visionModel = firstText(node, "vision_model", "visionModel");
                JsonNode visionReadyNode = first(node, "vision_ready", "visionReady");
                visionReady = visionReadyNode != null && visionReadyNode.asBoolean(false);
            }
        } catch (BusinessException ex) {
            log.info("智能服务健康检查失败：{}", ex.getMessage());
        }
        result.put("status", "DOWN".equalsIgnoreCase(aiStatus) ? "DEGRADED" : "UP");
        result.put("java", "UP");
        result.put("ai", aiStatus);
        result.put("mode", mode);
        result.put("knowledge", Maps.of("documents", documents, "chunks", chunks));
        // 同时输出嵌套 vector 对象与顶层 snake_case 字段，前端别名解析与验收均可取到
        result.put("vector", Maps.of("store", vectorStore, "embedding", embedding, "dim", vectorDim, "count", vectorCount));
        result.put("vector_store", vectorStore);
        result.put("embedding", embedding);
        result.put("vector_dim", vectorDim);
        result.put("vector_count", vectorCount);
        if (embeddingProvider.isBlank()) {
            embeddingProvider = "local";
        }
        if (modelSource.isBlank()) {
            modelSource = "real".equalsIgnoreCase(mode) ? "system" : "mock";
        }
        // v1.2 新增：模型 / 模型来源 / embedding provider / 是否支持用户自有 Key
        result.put("model", model);
        result.put("modelSource", modelSource);
        result.put("embeddingProvider", embeddingProvider);
        result.put("embeddingModel", embeddingModel);
        result.put("supportsUserKey", supportsUserKey);
        // v1.3：同时输出嵌套 vision 对象与顶层 snake_case 字段，前端/验收均可取到
        result.put("vision", Maps.of("provider", visionProvider, "model", visionModel, "ready", visionReady));
        result.put("vision_provider", visionProvider);
        result.put("vision_model", visionModel);
        result.put("vision_ready", visionReady);
        result.put("serverTime", LocalDateTime.now());
        return result;
    }

    /** 向量库名称：兼容字符串或 {name: ...} 对象两种形态 */
    private String vectorStoreName(JsonNode node) {
        JsonNode value = first(node, "vector_store", "vectorStore", "store", "vector_store_name");
        if (value == null || value.isNull()) {
            return "";
        }
        if (value.isObject()) {
            JsonNode name = first(value, "name", "store", "type");
            return name == null || name.isNull() ? "" : name.asText("");
        }
        return value.asText("");
    }

    private String text(JsonNode node, String field, String fallback) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() ? fallback : value.asText(fallback);
    }

    private int integer(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() || !value.isNumber() ? 0 : value.asInt();
    }

    private JsonNode first(JsonNode node, String... fields) {
        if (node == null) {
            return null;
        }
        for (String field : fields) {
            JsonNode value = node.get(field);
            if (value != null && !value.isNull()) {
                return value;
            }
        }
        return null;
    }

    private String firstText(JsonNode node, String... fields) {
        JsonNode value = first(node, fields);
        return value == null ? "" : value.asText("");
    }

    private int firstInteger(JsonNode node, String... fields) {
        JsonNode value = first(node, fields);
        return value == null || !value.isNumber() ? 0 : value.asInt();
    }
}
