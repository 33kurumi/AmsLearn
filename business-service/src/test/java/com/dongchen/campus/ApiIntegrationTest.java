package com.dongchen.campus;

import com.dongchen.campus.ai.AiServiceClient;
import com.dongchen.campus.common.BusinessException;
import com.dongchen.campus.common.ErrorCode;
import com.dongchen.campus.repository.StudentKpMasteryRepository;
import com.dongchen.campus.repository.UserRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 业务服务接口集成测试：鉴权、演示数据、教师配置校验、AI 降级与诊断主流程。
 */
@SpringBootTest
@AutoConfigureMockMvc
class ApiIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockitoBean
    private AiServiceClient aiServiceClient;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private StudentKpMasteryRepository masteryRepository;

    private String login(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("username", username, "password", password))))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode node = readTree(result);
        String token = node.path("data").path("token").asText();
        assertNotNull(token);
        assertTrue(!token.isBlank());
        return token;
    }

    private JsonNode readTree(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    private JsonNode readTree(String json) throws Exception {
        return objectMapper.readTree(json);
    }

    /** 学生知识点掌握度（S2）中某个知识点的 mastery。 */
    private double masteryOf(String token, String kpId) throws Exception {
        MvcResult result = mockMvc.perform(get("/api/student/knowledge-points")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn();
        for (JsonNode item : readTree(result).path("data")) {
            if (kpId.equals(item.path("kpId").asText())) {
                return item.path("mastery").asDouble();
            }
        }
        throw new IllegalStateException("未找到知识点 " + kpId);
    }

    @Test
    void healthIsPublicAndAggregatesAi() throws Exception {
        when(aiServiceClient.health()).thenReturn(readTree(
                "{\"status\":\"UP\",\"mode\":\"mock\",\"knowledge_documents\":5,"
                        + "\"knowledge_chunks\":180,\"model\":\"deepseek-chat\",\"llm_ready\":true,"
                        + "\"vector_store\":\"InMemoryVectorStore\",\"embedding\":\"LocalHashingEmbeddings\","
                        + "\"vector_dim\":384,\"vector_count\":180}"));
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.ai").value("UP"))
                .andExpect(jsonPath("$.data.java").value("UP"))
                .andExpect(jsonPath("$.data.knowledge.documents").value(5))
                .andExpect(jsonPath("$.data.vector_store").value("InMemoryVectorStore"))
                .andExpect(jsonPath("$.data.embedding").value("LocalHashingEmbeddings"))
                .andExpect(jsonPath("$.data.vector_dim").value(384))
                .andExpect(jsonPath("$.data.vector_count").value(180))
                .andExpect(jsonPath("$.data.vector.store").value("InMemoryVectorStore"))
                .andExpect(jsonPath("$.data.vector.embedding").value("LocalHashingEmbeddings"))
                .andExpect(jsonPath("$.data.vector.dim").value(384))
                .andExpect(jsonPath("$.data.vector.count").value(180))
                .andExpect(jsonPath("$.data.serverTime").exists());
    }

    @Test
    void healthDegradesWhenAiUnavailable() throws Exception {
        when(aiServiceClient.health())
                .thenThrow(new BusinessException(ErrorCode.AI_UNAVAILABLE, "智能服务暂不可用，请稍后重试", 503));
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.java").value("UP"))
                .andExpect(jsonPath("$.data.ai").value("DOWN"))
                .andExpect(jsonPath("$.data.vector_store").value(""))
                .andExpect(jsonPath("$.data.vector_dim").value(0))
                .andExpect(jsonPath("$.data.vector_count").value(0))
                .andExpect(jsonPath("$.data.vector.store").value(""))
                .andExpect(jsonPath("$.data.vector.count").value(0))
                .andExpect(jsonPath("$.data.vision.provider").value(""))
                .andExpect(jsonPath("$.data.vision.model").value(""))
                .andExpect(jsonPath("$.data.vision.ready").value(false))
                .andExpect(jsonPath("$.data.vision_ready").value(false));
    }

    @Test
    void protectedApiRequiresLogin() throws Exception {
        mockMvc.perform(get("/api/student/dashboard"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void loginSucceedsForDemoAccounts() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"student1\",\"password\":\"123456\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.user.username").value("student1"))
                .andExpect(jsonPath("$.data.user.role").value("STUDENT"))
                .andExpect(jsonPath("$.data.expiresAt").exists())
                .andReturn();
        assertTrue(readTree(result).path("data").path("token").asText().length() > 10);
    }

    @Test
    void loginFailsWithWrongPassword() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"student1\",\"password\":\"bad-password\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void studentCannotAccessTeacherApi() throws Exception {
        String token = login("student1", "123456");
        mockMvc.perform(get("/api/teacher/dashboard").header("Authorization", "Bearer " + token))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void metaKnowledgePointsReturnsAll67() throws Exception {
        String token = login("student1", "123456");
        mockMvc.perform(get("/api/meta/knowledge-points").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(67))
                .andExpect(jsonPath("$.data[0].kpId").value("kp001"))
                .andExpect(jsonPath("$.data[0].objectives").exists());
    }

    @Test
    void studentDashboardUsesPersistedDemoData() throws Exception {
        String token = login("student1", "123456");
        mockMvc.perform(get("/api/student/dashboard").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.user.username").value("student1"))
                .andExpect(jsonPath("$.data.classInfo.classId").value("C-GS-01"))
                .andExpect(jsonPath("$.data.mastery.totalKp").value(67))
                .andExpect(jsonPath("$.data.mastery.distribution.length()").value(5))
                .andExpect(jsonPath("$.data.weakTop5.length()").value(5))
                .andExpect(jsonPath("$.data.stats.interactionCount").isNumber())
                .andExpect(jsonPath("$.data.recentReports").isArray());
    }

    @Test
    void teacherConfigReadAndValidation() throws Exception {
        String token = login("teacher1", "123456");
        mockMvc.perform(get("/api/teacher/config").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.classId").value("C-GS-01"))
                .andExpect(jsonPath("$.data.answerMode").value("MIXED"))
                .andExpect(jsonPath("$.data.maxDifficulty").value(3))
                .andExpect(jsonPath("$.data.knowledgeScope.mode").value("ALL"))
                .andExpect(jsonPath("$.data.disabledTopics[0]").value("级数"));

        String body = "{\"answerMode\":\"MIXED\",\"maxDifficulty\":5,"
                + "\"knowledgeScope\":{\"mode\":\"ALL\",\"chapters\":[],\"kpIds\":[]},"
                + "\"boundaryRules\":\"仅解答高等数学范围内内容。\","
                + "\"kbAccess\":{\"kb1\":true,\"kb2\":true,\"kb3\":true,\"kb4\":false},"
                + "\"disabledTopics\":[]}";
        mockMvc.perform(put("/api/teacher/config")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void teacherKnowledgeListDegradesWhenAiDown() throws Exception {
        String token = login("teacher1", "123456");
        when(aiServiceClient.knowledgeDocuments(anyString()))
                .thenThrow(new BusinessException(ErrorCode.AI_UNAVAILABLE, "智能服务暂不可用，请稍后重试", 503));
        mockMvc.perform(get("/api/teacher/knowledge").header("Authorization", "Bearer " + token))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("AI_UNAVAILABLE"));
    }

    @Test
    void chatSavesInteractionRecord() throws Exception {
        String token = login("student1", "123456");
        when(aiServiceClient.qa(any())).thenReturn(readTree(
                "{\"answer\":\"当 x→0 时 sin x ~ x。\",\"sources\":[],\"blocked\":false,"
                        + "\"blockReason\":null,\"intent\":\"qa\","
                        + "\"action\":{\"type\":\"NONE\",\"label\":\"\",\"params\":null},"
                        + "\"kpIds\":[],\"mode\":\"mock\"}"));
        MvcResult result = mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"为什么 x 趋于 0 时 sin x 等价于 x？\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.reply").value("当 x→0 时 sin x ~ x。"))
                .andExpect(jsonPath("$.data.intent").value("qa"))
                .andExpect(jsonPath("$.data.blocked").value(false))
                .andExpect(jsonPath("$.data.knowledgeCovered").value(true))
                .andExpect(jsonPath("$.data.scopeWarning").doesNotExist())
                .andReturn();
        assertTrue(readTree(result).path("data").path("recordId").asLong() > 0);

        mockMvc.perform(get("/api/student/records?type=QA&page=1&size=10")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").isNumber())
                .andExpect(jsonPath("$.data.items[0].userMessage").exists());
    }

    @Test
    void chatPassesThroughKnowledgeCoveredAndScopeWarning() throws Exception {
        String token = login("student1", "123456");
        when(aiServiceClient.qa(any())).thenReturn(readTree(
                "{\"answer\":\"该问题超出高等数学课程范围。\",\"sources\":[],\"blocked\":false,"
                        + "\"blockReason\":null,\"intent\":\"qa\","
                        + "\"action\":{\"type\":\"NONE\",\"label\":\"\",\"params\":null},"
                        + "\"kpIds\":[],\"knowledgeCovered\":false,"
                        + "\"scopeWarning\":\"该问题超出高等数学课程范围，仅提供思路提示。\",\"mode\":\"mock\"}"));
        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"请证明黎曼猜想\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.knowledgeCovered").value(false))
                .andExpect(jsonPath("$.data.scopeWarning")
                        .value("该问题超出高等数学课程范围，仅提供思路提示。"));
    }

    @Test
    void diagnoseStartAndSubmitUpdatesMastery() throws Exception {
        String token = login("student1", "123456");
        when(aiServiceClient.diagnoseQuestions(any())).thenReturn(readTree(
                "{\"mode\":\"QUICK\",\"questions\":[{\"questionId\":\"q1\",\"index\":1,"
                        + "\"kpId\":\"kp001\",\"kpName\":\"函数的概念与性质\",\"difficulty\":2,"
                        + "\"type\":\"SINGLE\",\"stem\":\"函数 f(x)=x^2 的定义域是？\","
                        + "\"options\":[{\"key\":\"A\",\"text\":\"R\"},{\"key\":\"B\",\"text\":\"[0,+∞)\"}],"
                        + "\"hint\":\"先看定义域\",\"answerKey\":\"A\",\"analysis\":\"二次函数定义域为 R。\"}]}"));
        double before = masteryOf(token, "kp001");

        MvcResult started = mockMvc.perform(post("/api/diagnose/start")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"mode\":\"QUICK\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.questions[0].questionId").value("q1"))
                .andExpect(jsonPath("$.data.questions[0].answerKey").doesNotExist())
                .andExpect(jsonPath("$.data.questions[0].analysis").doesNotExist())
                .andReturn();
        long sessionId = readTree(started).path("data").path("sessionId").asLong();
        assertTrue(sessionId > 0);

        when(aiServiceClient.grade(any())).thenReturn(readTree(
                "{\"total\":1,\"correctCount\":1,\"score\":100,\"level\":\"优秀\","
                        + "\"results\":[{\"questionId\":\"q1\",\"kpId\":\"kp001\","
                        + "\"kpName\":\"函数的概念与性质\",\"correct\":true,\"errorType\":null,"
                        + "\"analysis\":\"二次函数定义域为 R。\",\"studentAnswer\":\"A\",\"correctAnswer\":\"A\"}],"
                        + "\"errorSummary\":[],\"advice\":[\"继续保持\"],\"mode\":\"mock\"}"));
        mockMvc.perform(post("/api/diagnose/" + sessionId + "/submit")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"answers\":[{\"questionId\":\"q1\",\"answer\":\"A\"}]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.correctCount").value(1))
                .andExpect(jsonPath("$.data.level").value("优秀"))
                .andExpect(jsonPath("$.data.report.status").value("COMPLETED"))
                .andExpect(jsonPath("$.data.masteryChanges[0].kpId").value("kp001"));

        double after = masteryOf(token, "kp001");
        assertTrue(after > before, "答对后掌握度应上升：" + before + " -> " + after);
        assertEquals(0.05, after - before, 1.0e-6);
    }

    @Test
    void wrongQuestionMarkReviewed() throws Exception {
        String token = login("student1", "123456");
        MvcResult list = mockMvc.perform(get("/api/student/wrong-questions?page=1&size=10")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.stats.total").isNumber())
                .andReturn();
        JsonNode items = readTree(list).path("data").path("items");
        assertTrue(items.size() > 0, "演示数据应包含错题");
        long id = items.get(0).path("id").asLong();
        mockMvc.perform(patch("/api/student/wrong-questions/" + id)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reviewed\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.reviewed").value(true));
    }

    @Test
    void plansListReturnsPersistedPlans() throws Exception {
        String token = login("student1", "123456");
        mockMvc.perform(get("/api/plans?page=1&size=10").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].id").exists())
                .andExpect(jsonPath("$.data.items[0].daysCount").isNumber())
                .andExpect(jsonPath("$.data.items[0].progress").isNumber());
    }

    // ==================== v1.2：用户 AI 配置 / 会话 / 健康字段 ====================

    /** 构造带 v1.2 字段的 /qa 响应，默认 real 模式 + 用户 Key。 */
    private JsonNode qaNode(String answer) throws Exception {
        return readTree(objectMapper.writeValueAsString(Map.of(
                "answer", answer,
                "intent", "qa",
                "blocked", false,
                "sources", List.of(),
                "kpIds", List.of(),
                "action", Map.of("type", "NONE", "label", "", "params", Map.of()),
                "mode", "real",
                "model", "deepseek-flash",
                "modelSource", "user",
                "knowledgeCovered", true)));
    }

    @Test
    void healthExposesV12ModelAndEmbeddingFields() throws Exception {
        when(aiServiceClient.health()).thenReturn(readTree(
                "{\"status\":\"UP\",\"mode\":\"real\",\"model\":\"deepseek-flash\","
                        + "\"modelSource\":\"system\",\"embedding_provider\":\"local\","
                        + "\"embedding_model\":\"LocalHashingEmbeddings\",\"supports_user_key\":true,"
                        + "\"knowledge_documents\":5,\"knowledge_chunks\":180}"));
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.mode").value("real"))
                .andExpect(jsonPath("$.data.model").value("deepseek-flash"))
                .andExpect(jsonPath("$.data.modelSource").value("system"))
                .andExpect(jsonPath("$.data.embeddingProvider").value("local"))
                .andExpect(jsonPath("$.data.embeddingModel").value("LocalHashingEmbeddings"))
                .andExpect(jsonPath("$.data.supportsUserKey").value(true));
    }

    @Test
    @SuppressWarnings("unchecked")
    void aiProfileMasksKeyAndPassesDecryptedKeyToAi() throws Exception {
        String token = login("student1", "123456");
        mockMvc.perform(get("/api/profile/ai").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.enabled").value(false))
                .andExpect(jsonPath("$.data.hasApiKey").value(false))
                .andExpect(jsonPath("$.data.apiKeyMasked").doesNotExist());

        MvcResult updated = mockMvc.perform(put("/api/profile/ai")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "apiKey", "sk-1234567890abcd",
                                "baseUrl", "https://api.deepseek.com",
                                "model", "deepseek-flash",
                                "enabled", true))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.enabled").value(true))
                .andExpect(jsonPath("$.data.hasApiKey").value(true))
                .andExpect(jsonPath("$.data.apiKeyMasked").value("sk-***abcd"))
                .andExpect(jsonPath("$.data.baseUrl").value("https://api.deepseek.com"))
                .andExpect(jsonPath("$.data.model").value("deepseek-flash"))
                .andReturn();
        // 密文落库：返回值里绝不出现明文 Key
        assertTrue(!readTree(updated).toString().contains("sk-1234567890abcd"));

        mockMvc.perform(put("/api/profile/ai")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("baseUrl", "http://api.deepseek.com"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));

        // 启用用户 Key 后，/api/chat 应把解密后的 Key 放进 llm 传给 AI
        when(aiServiceClient.qa(any())).thenReturn(qaNode("使用分部积分法可以得到结果。"));
        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("message", "求 ∫2xe^x dx"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.mode").value("real"))
                .andExpect(jsonPath("$.data.model").value("deepseek-flash"))
                .andExpect(jsonPath("$.data.modelSource").value("user"));

        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        verify(aiServiceClient).qa(captor.capture());
        Map<String, Object> llm = (Map<String, Object>) captor.getValue().get("llm");
        assertNotNull(llm, "启用用户 Key 后请求体应包含 llm");
        assertEquals("sk-1234567890abcd", llm.get("apiKey"));
        assertEquals("https://api.deepseek.com", llm.get("baseUrl"));
        assertEquals("deepseek-flash", llm.get("model"));

        mockMvc.perform(delete("/api/profile/ai").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.enabled").value(false))
                .andExpect(jsonPath("$.data.hasApiKey").value(false));
    }

    @Test
    @SuppressWarnings("unchecked")
    void conversationTracksHistoryAndRejectsOthers() throws Exception {
        String token = login("student1", "123456");
        String otherToken = login("student2", "123456");
        when(aiServiceClient.qa(any())).thenReturn(qaNode("当 x→0 时 sin x ~ x。"));

        MvcResult created = mockMvc.perform(post("/api/conversations")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("title", "极限讨论"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("极限讨论"))
                .andReturn();
        long conversationId = readTree(created).path("data").path("id").asLong();
        assertTrue(conversationId > 0);

        MvcResult first = mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "message", "sin x 为什么等价于 x？",
                                "conversationId", conversationId))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.conversationId").value(conversationId))
                .andReturn();
        long recordId = readTree(first).path("data").path("recordId").asLong();

        mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "message", "那 tan x 呢？",
                                "conversationId", conversationId))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.conversationId").value(conversationId));

        // 第二次问答必须带上该会话最近 6 条上下文（首轮 user + assistant）
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        verify(aiServiceClient, times(2)).qa(captor.capture());
        Map<String, Object> secondBody = captor.getAllValues().get(1);
        assertEquals(String.valueOf(conversationId), secondBody.get("conversationId"));
        List<Map<String, Object>> history = (List<Map<String, Object>>) secondBody.get("history");
        assertNotNull(history);
        assertEquals(2, history.size());
        assertEquals("user", history.get(0).get("role"));
        assertEquals("sin x 为什么等价于 x？", history.get(0).get("content"));
        assertEquals("assistant", history.get(1).get("role"));
        assertEquals("当 x→0 时 sin x ~ x。", history.get(1).get("content"));

        // 会话详情：2 轮 = 4 条消息，assistant 携带 v1.2 字段
        mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("极限讨论"))
                .andExpect(jsonPath("$.data.messages.length()").value(4))
                .andExpect(jsonPath("$.data.messages[0].role").value("user"))
                .andExpect(jsonPath("$.data.messages[1].role").value("assistant"))
                .andExpect(jsonPath("$.data.messages[1].recordId").value(recordId))
                .andExpect(jsonPath("$.data.messages[1].knowledgeCovered").value(true))
                .andExpect(jsonPath("$.data.messages[2].content").value("那 tan x 呢？"));

        // 列表按更新时间倒序，含 messageCount 与 lastMessage
        mockMvc.perform(get("/api/conversations?page=1&size=10")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].id").value(conversationId))
                .andExpect(jsonPath("$.data.items[0].messageCount").value(4))
                .andExpect(jsonPath("$.data.items[0].lastMessage").value("那 tan x 呢？"));

        // 学习记录带 conversationId
        MvcResult records = mockMvc.perform(get("/api/student/records?type=QA&page=1&size=50")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn();
        boolean found = false;
        for (JsonNode item : readTree(records).path("data").path("items")) {
            if (item.path("id").asLong() == recordId) {
                assertEquals(conversationId, item.path("conversationId").asLong());
                found = true;
            }
        }
        assertTrue(found, "学习记录列表应返回 conversationId");

        // 归属校验：其他学生 403，教师被学生端接口拦截 403
        mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
        String teacherToken = login("teacher1", "123456");
        mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + teacherToken))
                .andExpect(status().isForbidden());

        // 重命名 + 删除
        mockMvc.perform(patch("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("title", "极限与等价无穷小"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("极限与等价无穷小"));
        mockMvc.perform(delete("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound());
    }

    @Test
    void chatCreatesConversationWhenConversationIdMissing() throws Exception {
        String token = login("student3", "123456");
        when(aiServiceClient.qa(any())).thenReturn(qaNode("解析：使用分部积分法。"));
        MvcResult result = mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("message", "求 ∫2xe^x dx"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.conversationId").isNumber())
                .andReturn();
        long conversationId = readTree(result).path("data").path("conversationId").asLong();

        mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("求 ∫2xe^x dx"))
                .andExpect(jsonPath("$.data.messages.length()").value(2))
                .andExpect(jsonPath("$.data.messages[0].role").value("user"))
                .andExpect(jsonPath("$.data.messages[1].role").value("assistant"))
                .andExpect(jsonPath("$.data.messages[1].content").value("解析：使用分部积分法。"));
    }

    // ==================== v1.3：图片识别 / 前置自测 gate ====================

    /** gate（前置自测）响应：3 道单选前置题，不下发 answerKey。 */
    private String gateQuizJson() {
        return """
                {
                  "answer": "这道题涉及「级数」，属于教师配置的暂缓内容。我先用 3 道前置小题确认基础；通过后我会用三步带你学会它，不会直接给作业答案。",
                  "sources": [],
                  "blocked": false,
                  "blockReason": null,
                  "intent": "qa",
                  "action": {"type": "GATE", "label": "前置自测", "params": null},
                  "kpIds": ["kp055", "kp056"],
                  "knowledgeCovered": false,
                  "scopeWarning": null,
                  "mode": "real",
                  "model": "deepseek-flash",
                  "modelSource": "system",
                  "gate": {
                    "gateId": "g-8f3c2a1b",
                    "topic": "级数",
                    "state": "QUIZ",
                    "reason": "该问题涉及教师已禁用的内容「级数」",
                    "message": "通过后我会用三步带你学会「级数」。",
                    "prerequisites": [{"kpId": "kp028", "kpName": "原函数与不定积分的概念", "citation": "《高等数学教材讲义》第5章·第1节 原函数与不定积分的概念"}],
                    "questions": [
                      {"questionId": "gq1", "index": 1, "kpId": "kp028", "kpName": "原函数与不定积分的概念", "difficulty": 1, "stem": "下列哪个是 x^2 的一个原函数？", "options": [{"key": "A", "text": "2x"}, {"key": "B", "text": "x^3/3"}]},
                      {"questionId": "gq2", "index": 2, "kpId": "kp028", "kpName": "原函数与不定积分的概念", "difficulty": 1, "stem": "不定积分的结果应包含？", "options": [{"key": "A", "text": "常数 C"}, {"key": "B", "text": "无常数"}]},
                      {"questionId": "gq3", "index": 3, "kpId": "kp029", "kpName": "不定积分的性质", "difficulty": 2, "stem": "∫f'(x)dx = ?", "options": [{"key": "A", "text": "f(x)+C"}, {"key": "B", "text": "f'(x)+C"}]}
                    ],
                    "score": null,
                    "total": 3
                  }
                }
                """;
    }

    /** gate/check 通过响应：2/3 以上通过，返回三步教学与答案。 */
    private String gateCheckPassedJson() {
        return """
                {
                  "passed": true,
                  "score": 3,
                  "total": 3,
                  "state": "PASSED",
                  "feedback": "前置基础已确认，下面按三个步骤带你学会「级数」。",
                  "answer": "### 第 1 步：补齐前置\\n回顾原函数与不定积分的概念。\\n\\n### 第 2 步：建立概念\\n理解级数收敛的定义。\\n\\n### 第 3 步：带做一题\\n跟着算一道判别题。",
                  "sources": [{"citation": "《高等数学教材讲义》第5章·第1节", "chapter": "第5章", "section": "第1节"}],
                  "knowledgeCovered": true,
                  "gate": {
                    "gateId": "g-test01",
                    "topic": "级数",
                    "state": "PASSED",
                    "reason": "该问题涉及教师已禁用的内容「级数」",
                    "message": "通过后我会用三步带你学会「级数」。",
                    "prerequisites": [{"kpId": "kp028", "kpName": "原函数与不定积分的概念"}],
                    "questions": [],
                    "score": 3,
                    "total": 3
                  },
                  "teaching": {"steps": [{"title": "第 1 步：补齐前置", "content": "回顾原函数与不定积分的概念。"}, {"title": "第 2 步：建立概念", "content": "理解级数收敛的定义。"}, {"title": "第 3 步：带做一题", "content": "跟着算一道判别题。"}], "practice": "建议自测：判断级数敛散性。"},
                  "mode": "real",
                  "model": "deepseek-flash",
                  "modelSource": "system"
                }
                """;
    }

    @Test
    void visionRejectsInvalidFileAndForwardsImage() throws Exception {
        String token = login("student1", "123456");

        // 未携带 file 部件：400 而非 500
        mockMvc.perform(multipart("/api/student/chat/vision")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value("缺少参数 file"));

        // 非图片：400 且不调用 AI
        MockMultipartFile textFile = new MockMultipartFile("file", "notes.txt", "text/plain",
                "not an image".getBytes(StandardCharsets.UTF_8));
        mockMvc.perform(multipart("/api/student/chat/vision").file(textFile)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value("仅支持 png/jpeg/webp/gif 格式的图片"));
        verify(aiServiceClient, times(0)).visionExtract(any());

        // 超过 5MB：400
        MockMultipartFile bigFile = new MockMultipartFile("file", "big.png", "image/png",
                new byte[5 * 1024 * 1024 + 1]);
        mockMvc.perform(multipart("/api/student/chat/vision").file(bigFile)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value("图片大小不能超过 5MB"));
        verify(aiServiceClient, times(0)).visionExtract(any());

        // 正常图片：转发 AI 并原样返回识别结果
        when(aiServiceClient.visionExtract(any())).thenReturn(readTree("""
                {"ok": true, "text": "已知函数 f(x)=x^3-3x^2+2，求 f'(x)。", "model": "Qwen/Qwen3-VL-8B-Instruct", "provider": "siliconflow", "message": null}
                """));
        MockMultipartFile imageFile = new MockMultipartFile("file", "question.png", "image/png",
                new byte[]{1, 2, 3, 4});
        mockMvc.perform(multipart("/api/student/chat/vision").file(imageFile)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.ok").value(true))
                .andExpect(jsonPath("$.data.text").value("已知函数 f(x)=x^3-3x^2+2，求 f'(x)。"))
                .andExpect(jsonPath("$.data.provider").value("siliconflow"))
                .andExpect(jsonPath("$.data.model").value("Qwen/Qwen3-VL-8B-Instruct"));
        verify(aiServiceClient).visionExtract(any());
    }

    @Test
    void chatPassesThroughGateAndPersistsIt() throws Exception {
        String token = login("student3", "123456");
        when(aiServiceClient.qa(any())).thenReturn(readTree(gateQuizJson()));
        MvcResult result = mockMvc.perform(post("/api/chat")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("message", "级数怎么判断敛散性？"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.action.type").value("GATE"))
                .andExpect(jsonPath("$.data.gate.gateId").value("g-8f3c2a1b"))
                .andExpect(jsonPath("$.data.gate.state").value("QUIZ"))
                .andExpect(jsonPath("$.data.gate.questions.length()").value(3))
                .andExpect(jsonPath("$.data.gate.questions[0].answerKey").doesNotExist())
                .andReturn();
        JsonNode data = readTree(result).path("data");
        long conversationId = data.path("conversationId").asLong();
        assertTrue(conversationId > 0);

        // gate 随记录落库，会话详情里 assistant 消息能读回
        mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.messages.length()").value(2))
                .andExpect(jsonPath("$.data.messages[1].gate.gateId").value("g-8f3c2a1b"))
                .andExpect(jsonPath("$.data.messages[1].gate.state").value("QUIZ"))
                .andExpect(jsonPath("$.data.messages[1].gate.questions.length()").value(3));
    }

    @Test
    void gateCheckRequiresGateId() throws Exception {
        String token = login("student1", "123456");
        mockMvc.perform(post("/api/student/gate/check")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"conversationId\":1,\"answers\":[{\"questionId\":\"gq1\",\"choice\":\"A\"}]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value("gateId 不能为空"));
        verify(aiServiceClient, times(0)).gateCheck(any());
    }

    @Test
    void teacherCannotSubmitGateCheck() throws Exception {
        String token = login("teacher1", "123456");
        mockMvc.perform(post("/api/student/gate/check")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"gateId\":\"g-1\",\"conversationId\":1,"
                                + "\"answers\":[{\"questionId\":\"gq1\",\"choice\":\"A\"}]}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void gateCheckPassedReturnsTeachingAndPersistsMessages() throws Exception {
        String token = login("student1", "123456");
        MvcResult created = mockMvc.perform(post("/api/conversations")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("title", "级数前置自测"))))
                .andExpect(status().isOk())
                .andReturn();
        long conversationId = readTree(created).path("data").path("id").asLong();

        when(aiServiceClient.gateCheck(any())).thenReturn(readTree(gateCheckPassedJson()));
        MvcResult checked = mockMvc.perform(post("/api/student/gate/check")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "gateId", "g-test01",
                                "conversationId", conversationId,
                                "answers", List.of(
                                        Map.of("questionId", "gq1", "choice", "B"),
                                        Map.of("questionId", "gq2", "choice", "A"),
                                        Map.of("questionId", "gq3", "choice", "A"))))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.passed").value(true))
                .andExpect(jsonPath("$.data.score").value(3))
                .andExpect(jsonPath("$.data.total").value(3))
                .andExpect(jsonPath("$.data.state").value("PASSED"))
                .andExpect(jsonPath("$.data.conversationId").value(conversationId))
                .andExpect(jsonPath("$.data.gate.gateId").value("g-test01"))
                .andExpect(jsonPath("$.data.teaching.steps.length()").value(3))
                .andExpect(jsonPath("$.data.recordId").isNumber())
                .andReturn();
        assertTrue(readTree(checked).path("data").path("recordId").asLong() > 0);

        // 转发 AI 的请求体：gateId + conversationId 字符串 + 3 个答案
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        verify(aiServiceClient).gateCheck(captor.capture());
        Map<String, Object> body = captor.getValue();
        assertEquals("g-test01", body.get("gateId"));
        assertEquals(String.valueOf(conversationId), body.get("conversationId"));
        assertEquals(3, ((List<?>) body.get("answers")).size());

        // 会话内表现为 user/assistant 两条消息，assistant 携带 gate
        MvcResult detail = mockMvc.perform(get("/api/conversations/" + conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.messages.length()").value(2))
                .andExpect(jsonPath("$.data.messages[0].role").value("user"))
                .andExpect(jsonPath("$.data.messages[0].content").value("前置测试提交（3 题）"))
                .andExpect(jsonPath("$.data.messages[1].role").value("assistant"))
                .andExpect(jsonPath("$.data.messages[1].gate.gateId").value("g-test01"))
                .andExpect(jsonPath("$.data.messages[1].gate.state").value("PASSED"))
                .andReturn();
        String assistantContent = readTree(detail).path("data").path("messages").get(1).path("content").asText();
        assertTrue(assistantContent.contains("第 1 步"), "assistant 消息应保存三步教学答案");
    }

    @Test
    void healthExposesVisionFields() throws Exception {
        when(aiServiceClient.health()).thenReturn(readTree("""
                {"status": "UP", "mode": "real", "model": "deepseek-flash",
                 "vision_provider": "siliconflow", "vision_model": "Qwen/Qwen3-VL-8B-Instruct", "vision_ready": true}
                """));
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.vision.provider").value("siliconflow"))
                .andExpect(jsonPath("$.data.vision.model").value("Qwen/Qwen3-VL-8B-Instruct"))
                .andExpect(jsonPath("$.data.vision.ready").value(true))
                .andExpect(jsonPath("$.data.vision_provider").value("siliconflow"))
                .andExpect(jsonPath("$.data.vision_model").value("Qwen/Qwen3-VL-8B-Instruct"))
                .andExpect(jsonPath("$.data.vision_ready").value(true));
    }

    // ==================== v1.4：注册 / 教师重置学生密码 ====================

    private static final AtomicInteger USER_SEQ = new AtomicInteger();

    /** 生成符合 ^[A-Za-z0-9_]{4,20}$ 的唯一用户名，避免测试间相互污染。 */
    private String uniqueUsername(String prefix) {
        return prefix + Long.toString(System.currentTimeMillis(), 36) + USER_SEQ.incrementAndGet();
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder registerRequest(
            String username, String password, String displayName, String email) throws Exception {
        return post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(Map.of(
                        "username", username,
                        "password", password,
                        "displayName", displayName,
                        "email", email)));
    }

    @Test
    void registerCreatesStudentWithMasteryAndLogsIn() throws Exception {
        String username = uniqueUsername("stu_");
        String password = "reg-pass-2026";
        MvcResult registered = mockMvc.perform(registerRequest(username, password, "新注册同学", "new@example.com"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.user.username").value(username))
                .andExpect(jsonPath("$.data.user.displayName").value("新注册同学"))
                .andExpect(jsonPath("$.data.user.role").value("STUDENT"))
                .andExpect(jsonPath("$.data.user.classId").value("C-GS-01"))
                .andExpect(jsonPath("$.data.expiresAt").exists())
                .andReturn();
        JsonNode data = readTree(registered).path("data");
        String token = data.path("token").asText();
        long studentId = data.path("user").path("id").asLong();
        assertTrue(token.length() > 10);
        assertTrue(studentId > 0);

        // 67 条知识点掌握度已初始化（mastery=0）
        assertEquals(67, masteryRepository.findByStudentId(studentId).size());
        assertEquals(0.0, masteryOf(token, "kp001"), 1.0e-9);

        // 注册即登录：令牌可直接访问学生端接口
        mockMvc.perform(get("/api/student/dashboard").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.user.username").value(username))
                .andExpect(jsonPath("$.data.mastery.totalKp").value(67))
                .andExpect(jsonPath("$.data.mastery.avg").value(0.0));

        // 密码可再次登录
        String reloginToken = login(username, password);
        assertTrue(reloginToken.length() > 10);
    }

    @Test
    void registerRejectsDuplicateUsername() throws Exception {
        String username = uniqueUsername("dup_");
        mockMvc.perform(registerRequest(username, "123456", "重复用户", "dup@example.com"))
                .andExpect(status().isOk());
        mockMvc.perform(registerRequest(username, "123456", "重复用户", "dup@example.com"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.code").value("CONFLICT"))
                .andExpect(jsonPath("$.message").value("用户名已存在，请更换"));
    }

    @Test
    void registerRejectsInvalidFields() throws Exception {
        // 弱密码
        mockMvc.perform(registerRequest(uniqueUsername("weak_"), "123", "弱密码", "weak@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("password")));
        // 用户名不合法
        mockMvc.perform(registerRequest("ab", "123456", "短用户名", "short@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("username")));
        // 昵称为空（去空格后）
        mockMvc.perform(registerRequest(uniqueUsername("nick_"), "123456", "   ", "nick@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("displayName")));
    }

    @Test
    void teacherResetsStudentPasswordSoOldFailsAndNewWorks() throws Exception {
        String username = uniqueUsername("reset_");
        MvcResult registered = mockMvc.perform(registerRequest(username, "old-pass-2026", "待重置", "reset@example.com"))
                .andExpect(status().isOk())
                .andReturn();
        long studentId = readTree(registered).path("data").path("user").path("id").asLong();

        String teacherToken = login("teacher1", "123456");
        mockMvc.perform(put("/api/teacher/students/" + studentId + "/password")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"newPassword\":\"new-pass-2026\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data").value(org.hamcrest.Matchers.nullValue()));

        // 旧密码立即失效
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "username", username, "password", "old-pass-2026"))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));

        // 新密码立即生效
        assertTrue(login(username, "new-pass-2026").length() > 10);

        // 弱密码 400（受限字段 newPassword）
        mockMvc.perform(put("/api/teacher/students/" + studentId + "/password")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"newPassword\":\"123\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("newPassword")));
    }

    @Test
    void teacherCanOnlyResetOwnClassStudentPassword() throws Exception {
        String teacherToken = login("teacher1", "123456");
        String teacher2Token = login("teacher2", "123456");

        // teacher2 班上的学生：teacher1 重置 → 403
        MvcResult teacher2Students = mockMvc.perform(get("/api/teacher/students")
                        .header("Authorization", "Bearer " + teacher2Token))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode others = readTree(teacher2Students).path("data");
        assertTrue(others.size() > 0, "C-GS-02 应有演示学生");
        long otherClassStudentId = others.get(0).path("id").asLong();
        mockMvc.perform(put("/api/teacher/students/" + otherClassStudentId + "/password")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"newPassword\":\"new-pass-2026\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"))
                .andExpect(jsonPath("$.message").value("只能重置本班学生的密码"));

        // 目标是教师账号 → 403
        long teacher2Id = userRepository.findByUsername("teacher2").orElseThrow().getId();
        mockMvc.perform(put("/api/teacher/students/" + teacher2Id + "/password")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"newPassword\":\"new-pass-2026\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));

        // 学生不存在 → 404
        mockMvc.perform(put("/api/teacher/students/999999/password")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"newPassword\":\"new-pass-2026\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("NOT_FOUND"))
                .andExpect(jsonPath("$.message").value("学生不存在"));

        // 学生调用教师接口 → 403
        String studentToken = login("student1", "123456");
        mockMvc.perform(put("/api/teacher/students/3/password")
                        .header("Authorization", "Bearer " + studentToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"newPassword\":\"new-pass-2026\"}"))
                .andExpect(status().isForbidden());
    }
}
