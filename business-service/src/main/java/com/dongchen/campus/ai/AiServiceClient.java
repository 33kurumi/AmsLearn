package com.dongchen.campus.ai;

import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.config.AiProperties;
import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriBuilder;

import java.io.IOException;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;

/**
 * FastAPI 智能服务客户端：/health、/qa、/diagnose/**、/practice/**、/plan、/class-analysis、
 * /config/extract、/knowledge/**。统一返回 JsonNode，错误转换为契约错误码。
 */
@Component
public class AiServiceClient {

    private static final Logger log = LoggerFactory.getLogger(AiServiceClient.class);
    private static final String UNAVAILABLE_MESSAGE = "智能服务暂不可用，请稍后重试";

    private final RestClient restClient;
    private final JsonHelper jsonHelper;

    public AiServiceClient(AiProperties properties, JsonHelper jsonHelper) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeoutMs()))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofMillis(properties.getReadTimeoutMs()));
        this.restClient = RestClient.builder()
                .baseUrl(properties.getBaseUrl())
                .requestFactory(factory)
                .build();
        this.jsonHelper = jsonHelper;
    }

    public JsonNode health() {
        return get("/health");
    }

    public JsonNode qa(Map<String, Object> body) {
        return post("/qa", body);
    }

    /** v1.3 前置自测提交：转发 AI /qa/gate/check。 */
    public JsonNode gateCheck(Map<String, Object> body) {
        return post("/qa/gate/check", body);
    }

    public JsonNode intent(Map<String, Object> body) {
        return post("/intent", body);
    }

    public JsonNode retrieve(Map<String, Object> body) {
        return post("/retrieve", body);
    }

    public JsonNode diagnoseQuestions(Map<String, Object> body) {
        return post("/diagnose/questions", body);
    }

    public JsonNode grade(Map<String, Object> body) {
        return post("/diagnose/grade", body);
    }

    public JsonNode practiceQuestions(Map<String, Object> body) {
        return post("/practice/questions", body);
    }

    public JsonNode practiceHint(Map<String, Object> body) {
        return post("/practice/hint", body);
    }

    public JsonNode plan(Map<String, Object> body) {
        return post("/plan", body);
    }

    public JsonNode classAnalysis(Map<String, Object> body) {
        return post("/class-analysis", body);
    }

    public JsonNode configExtract(Map<String, Object> body) {
        return post("/config/extract", body);
    }

    public JsonNode knowledgeDocuments(String classId) {
        try {
            String raw = restClient.get()
                    .uri(uriBuilder -> {
                        UriBuilder builder = uriBuilder.path("/knowledge/documents");
                        if (classId != null && !classId.isBlank()) {
                            builder.queryParam("classId", classId);
                        }
                        return builder.build();
                    })
                    .retrieve()
                    .body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    public JsonNode knowledgeUpload(MultipartFile file, String kb, String classId, Long uploadedBy) {
        byte[] bytes;
        try {
            bytes = file.getBytes();
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "上传文件读取失败");
        }
        String filename = file.getOriginalFilename() == null ? "upload.md" : file.getOriginalFilename();
        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        };
        MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
        parts.add("file", resource);
        parts.add("kb", kb);
        if (classId != null && !classId.isBlank()) {
            parts.add("classId", classId);
        }
        if (uploadedBy != null) {
            parts.add("uploadedBy", String.valueOf(uploadedBy));
        }
        try {
            String raw = restClient.post()
                    .uri("/knowledge/upload")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(parts)
                    .retrieve()
                    .body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    /** v1.3 图片识别：multipart（字段 file）转发 AI /vision/extract，AI 不可达映射 503。 */
    public JsonNode visionExtract(MultipartFile file) {
        byte[] bytes;
        try {
            bytes = file.getBytes();
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.VALIDATION_ERROR, "上传文件读取失败");
        }
        String original = file.getOriginalFilename();
        String filename = original == null || original.isBlank() ? "image.png" : original;
        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        };
        HttpHeaders partHeaders = new HttpHeaders();
        try {
            partHeaders.setContentType(file.getContentType() == null || file.getContentType().isBlank()
                    ? MediaType.APPLICATION_OCTET_STREAM
                    : MediaType.parseMediaType(file.getContentType()));
        } catch (IllegalArgumentException ex) {
            partHeaders.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        }
        MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
        parts.add("file", new HttpEntity<>(resource, partHeaders));
        try {
            String raw = restClient.post()
                    .uri("/vision/extract")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(parts)
                    .retrieve()
                    .body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    public JsonNode knowledgeToggle(String documentId, boolean enabled) {
        return patch("/knowledge/documents/" + documentId, Map.of("enabled", enabled));
    }

    public JsonNode knowledgeDelete(String documentId) {
        try {
            String raw = restClient.delete()
                    .uri("/knowledge/documents/{id}", documentId)
                    .retrieve()
                    .body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    public JsonNode knowledgeRebuild() {
        return post("/knowledge/rebuild", Map.of());
    }

    private JsonNode get(String path) {
        try {
            String raw = restClient.get().uri(path).retrieve().body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    private JsonNode post(String path, Object body) {
        try {
            String raw = restClient.post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    private JsonNode patch(String path, Object body) {
        try {
            String raw = restClient.patch()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(String.class);
            return parse(raw);
        } catch (RestClientResponseException ex) {
            throw mapError(ex);
        } catch (ResourceAccessException ex) {
            throw unavailable(ex);
        }
    }

    private JsonNode parse(String raw) {
        try {
            return jsonHelper.readTree(raw == null || raw.isBlank() ? "{}" : raw);
        } catch (BusinessException ex) {
            throw new BusinessException(ErrorCode.AI_UNAVAILABLE, "智能服务返回数据格式异常", 503);
        }
    }

    private BusinessException unavailable(Exception ex) {
        log.warn("调用智能服务失败: {}", ex.getMessage());
        return new BusinessException(ErrorCode.AI_UNAVAILABLE, UNAVAILABLE_MESSAGE, 503);
    }

    private BusinessException mapError(RestClientResponseException ex) {
        int status = ex.getStatusCode().value();
        String detail = extractDetail(ex.getResponseBodyAsString());
        log.warn("智能服务返回错误 status={} detail={}", status, detail);
        if (status >= 500) {
            return new BusinessException(ErrorCode.AI_UNAVAILABLE, UNAVAILABLE_MESSAGE, 503);
        }
        if (status == 400 || status == 404 || status == 422) {
            return new BusinessException(ErrorCode.VALIDATION_ERROR,
                    detail == null || detail.isBlank() ? "智能服务请求参数错误" : detail,
                    400);
        }
        return new BusinessException(ErrorCode.AI_UNAVAILABLE, UNAVAILABLE_MESSAGE, 503);
    }

    private String extractDetail(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            JsonNode node = jsonHelper.mapper().readTree(raw);
            JsonNode detail = node.get("detail");
            if (detail != null && !detail.isNull()) {
                return detail.isTextual() ? detail.asText() : detail.toString();
            }
        } catch (Exception ignored) {
            // 非 JSON 响应，回退到截断原文
        }
        return raw.length() > 200 ? raw.substring(0, 200) : raw;
    }
}
