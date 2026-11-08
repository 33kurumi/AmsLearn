"""AI 服务请求/响应模型。

字段名严格对齐 docs/01-接口约定.md 第 4.3/4.4 节与第 5 节；只做字段增补，不改名。
请求模型对缺省字段给出安全默认值，便于 Java 侧逐步接入。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# 通用结构（契约 3.6）
# --------------------------------------------------------------------------
class Option(BaseModel):
    key: str = ""
    text: str = ""


class Question(BaseModel):
    questionId: str = ""
    index: int = 0
    kpId: str | None = None
    kpName: str | None = None
    difficulty: int = 1
    type: str = "SINGLE"
    stem: str = ""
    options: list[Option] = Field(default_factory=list)
    hint: str = ""
    answerKey: str | None = None
    analysis: str | None = None
    layer: str | None = None
    errorType: str | None = None


class SourceRef(BaseModel):
    documentId: str = ""
    kb: str = ""
    title: str = ""
    excerpt: str = ""
    score: float = 0.0
    kpId: str | None = None
    chunkId: str = ""
    chapter: str | None = None
    section: str | None = None
    citation: str = ""


class MasteryItem(BaseModel):
    kpId: str = ""
    kpName: str = ""
    mastery: float = 0.0
    attempts: int = 0
    correctCount: int = 0
    chapter: str | None = None


class TeacherConfig(BaseModel):
    """Java 在调用前已把 knowledgeScope 解析为 effectiveKpIds（[] 表示全部）。"""

    answerMode: str = "MIXED"
    maxDifficulty: int = 3
    effectiveKpIds: list[str] = Field(default_factory=list)
    boundaryRules: str = ""
    disabledTopics: list[str] = Field(default_factory=list)
    kbAccess: dict[str, bool] = Field(default_factory=dict)


class HistoryItem(BaseModel):
    role: str = "user"
    content: str = ""


class ActionVO(BaseModel):
    type: str = "NONE"
    label: str = ""
    params: dict | None = None


class AdviceItem(BaseModel):
    title: str = ""
    content: str = ""
    priority: str = "MEDIUM"


# --------------------------------------------------------------------------
# AI2 /qa  AI3 /intent  AI4 /retrieve
# --------------------------------------------------------------------------
class LLMOverride(BaseModel):
    """v1.2：用户自带 key/模型，仅本次请求有效，绝不写日志/落库。"""

    apiKey: str = ""
    baseUrl: str = ""
    model: str = ""


class GatePrerequisite(BaseModel):
    """前置自测涉及的前置知识点。"""

    kpId: str = ""
    kpName: str = ""
    citation: str = ""


class GateQuestion(BaseModel):
    """前置自测题（绝不包含 answerKey/analysis）。"""

    questionId: str = ""
    index: int = 0
    kpId: str = ""
    kpName: str = ""
    difficulty: int = 1
    stem: str = ""
    options: list[Option] = Field(default_factory=list)


class Gate(BaseModel):
    """v1.3 教师超纲内容的「前置自测」状态。"""

    gateId: str = ""
    topic: str = ""
    state: str = "QUIZ"  # QUIZ | PASSED | FAILED | EXPIRED
    reason: str = ""
    message: str = ""
    prerequisites: list[GatePrerequisite] = Field(default_factory=list)
    questions: list[GateQuestion] = Field(default_factory=list)
    score: int | None = None
    total: int = 3


class TeachingStep(BaseModel):
    title: str = ""
    content: str = ""


class Teaching(BaseModel):
    """通过前置测试后的循序渐进教学（固定三步）。"""

    steps: list[TeachingStep] = Field(default_factory=list)
    practice: str = ""


class QARequest(BaseModel):
    userId: int = 0
    role: str = "STUDENT"
    classId: str | None = None
    message: str = ""
    # v1.2：多轮上下文 + 会话标识（AI 侧只取最后 8 条 / 合计 ≤4000 字符）
    conversationId: str | None = None
    history: list[HistoryItem] = Field(default_factory=list)
    teacherConfig: TeacherConfig | None = None
    mastery: list[MasteryItem] = Field(default_factory=list)
    llm: LLMOverride | None = None


class QAResponse(BaseModel):
    answer: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    blocked: bool = False
    blockReason: str | None = None
    intent: str = "qa"
    action: ActionVO = Field(default_factory=ActionVO)
    kpIds: list[str] = Field(default_factory=list)
    # 契约 v1.1：是否命中知识库；无命中时是否给出范围软提醒（非数学类）
    knowledgeCovered: bool = True
    scopeWarning: str | None = None
    mode: str = "mock"
    # v1.2：本次实际使用的模型与其来源
    # system=系统 key / user=用户自带 key / mock=演示逻辑 / none=规则拦截（未调用模型）
    model: str = ""
    modelSource: str = "mock"
    conversationId: str | None = None
    # v1.3：教师超纲内容的前置自测；非 gate 场景为 null
    gate: Gate | None = None


class GateAnswerItem(BaseModel):
    questionId: str = ""
    choice: str = ""


class GateCheckRequest(BaseModel):
    """v1.3 前置自测提交。conversationId 允许字符串或数字，服务端统一转 str。"""

    gateId: str = ""
    conversationId: str | int | None = None
    answers: list[GateAnswerItem] = Field(default_factory=list)


class GateCheckResponse(BaseModel):
    passed: bool = False
    score: int = 0
    total: int = 0
    state: str = "QUIZ"  # PASSED | FAILED | EXPIRED
    feedback: str = ""
    answer: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    knowledgeCovered: bool = False
    gate: Gate | None = None
    teaching: Teaching | None = None
    mode: str = "mock"
    model: str | None = None
    modelSource: str = "mock"


class IntentRequest(BaseModel):
    message: str = ""
    role: str = "STUDENT"


class IntentResponse(BaseModel):
    intent: str = "unknown"
    confidence: float = 0.0
    kpIds: list[str] = Field(default_factory=list)
    reason: str = ""
    mode: str = "mock"


class RetrieveRequest(BaseModel):
    query: str = ""
    topK: int = 8
    minScore: float | None = None  # 不传则按当前 embedding 方案取默认阈值
    kbScope: list[str] = Field(default_factory=lambda: ["KB1", "KB2", "KB3", "KB4"])
    classId: str | None = None


class RetrieveResponse(BaseModel):
    items: list[SourceRef] = Field(default_factory=list)
    enough: bool = False
    topScore: float = 0.0
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI5 /diagnose/questions  AI6 /diagnose/grade
# --------------------------------------------------------------------------
class DiagnoseQuestionsRequest(BaseModel):
    mode: str = "QUICK"
    count: int = 0
    difficultyMax: int = 0
    kpIds: list[str] = Field(default_factory=list)
    mastery: list[MasteryItem] = Field(default_factory=list)
    classId: str | None = None
    teacherConfig: TeacherConfig | None = None


class QuestionsResponse(BaseModel):
    questions: list[Question] = Field(default_factory=list)
    mode: str = "mock"


class AnswerItem(BaseModel):
    questionId: str = ""
    answer: str = ""


class GradeRequest(BaseModel):
    questions: list[Question] = Field(default_factory=list)
    answers: list[AnswerItem] = Field(default_factory=list)


class GradeResultItem(BaseModel):
    questionId: str = ""
    kpId: str | None = None
    kpName: str | None = None
    correct: bool = False
    errorType: str | None = None
    analysis: str = ""
    studentAnswer: str = ""
    correctAnswer: str = ""


class ErrorSummaryItem(BaseModel):
    errorType: str = ""
    count: int = 0
    ratio: float = 0.0


class GradeResponse(BaseModel):
    total: int = 0
    correctCount: int = 0
    score: int = 0
    level: str = "待提升"
    results: list[GradeResultItem] = Field(default_factory=list)
    errorSummary: list[ErrorSummaryItem] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI7 /practice/questions  AI8 /practice/hint
# --------------------------------------------------------------------------
class PracticeQuestionsRequest(BaseModel):
    layer: str = "A"
    count: int = 0
    difficultyMax: int = 4
    kpIds: list[str] = Field(default_factory=list)
    classId: str | None = None
    teacherConfig: TeacherConfig | None = None


class PracticeQuestionsResponse(BaseModel):
    questions: list[Question] = Field(default_factory=list)
    guidance: str = ""
    mode: str = "mock"


class HintRequest(BaseModel):
    question: Question = Field(default_factory=Question)
    studentAnswer: str = ""
    teacherConfig: TeacherConfig | None = None


class HintResponse(BaseModel):
    hint: str = ""
    strategy: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI9 /plan
# --------------------------------------------------------------------------
class PlanRequest(BaseModel):
    period: str = "WEEK"
    days: int = 7
    focusKpIds: list[str] = Field(default_factory=list)
    goal: str = ""
    mastery: list[MasteryItem] = Field(default_factory=list)
    classId: str | None = None
    teacherConfig: TeacherConfig | None = None


class StudyPart(BaseModel):
    summary: str = ""
    points: list[str] = Field(default_factory=list)
    example: str = ""


class ReviewPart(BaseModel):
    summary: str = ""
    checklist: list[str] = Field(default_factory=list)


class PlanDay(BaseModel):
    dayIndex: int = 0
    date: str | None = None
    kpId: str = ""
    kpName: str = ""
    goal: str = ""
    study: StudyPart = Field(default_factory=StudyPart)
    practiceQuestions: list[Question] = Field(default_factory=list)
    review: ReviewPart = Field(default_factory=ReviewPart)


class PlanResponse(BaseModel):
    summary: str = ""
    days: list[PlanDay] = Field(default_factory=list)
    period: str = "WEEK"
    daysCount: int = 0
    title: str = ""
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI10 /class-analysis
# --------------------------------------------------------------------------
class ClassAnalysisRequest(BaseModel):
    period: str = "7D"
    classId: str | None = None
    className: str = ""
    subject: str = "高等数学"
    studentCount: int = 0
    totalInteractions: int = 0
    activeStudents: int = 0
    accuracy: float = 0.0
    masteryDistribution: list[dict] = Field(default_factory=list)
    weakKps: list[dict] = Field(default_factory=list)
    errorStats: list[dict] = Field(default_factory=list)
    hotQuestions: list[dict] = Field(default_factory=list)
    ranking: list[dict] = Field(default_factory=list)
    teacherConfig: TeacherConfig | None = None


class ClassAnalysisResponse(BaseModel):
    overview: dict = Field(default_factory=dict)
    weakTop10: list[dict] = Field(default_factory=list)
    errorSummary: list[dict] = Field(default_factory=list)
    hotQuestions: list[dict] = Field(default_factory=list)
    ranking: list[dict] = Field(default_factory=list)
    advice: list[AdviceItem] = Field(default_factory=list)
    summary: str = ""
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI11 /config/extract
# --------------------------------------------------------------------------
class ConfigExtractRequest(BaseModel):
    text: str = ""
    current: dict = Field(default_factory=dict)


class ConfigExtractResponse(BaseModel):
    patch: dict = Field(default_factory=dict)
    explanation: str = ""
    unrecognized: list[str] = Field(default_factory=list)
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI12-AI16 知识库管理
# --------------------------------------------------------------------------
class KnowledgePatchRequest(BaseModel):
    enabled: bool = True


class DocumentVO(BaseModel):
    documentId: str = ""
    name: str = ""
    kb: str = ""
    scope: str = "GLOBAL"
    classId: str | None = None
    chunks: int = 0
    enabled: bool = True
    size: int = 0
    uploadedAt: str | None = None
    uploadedBy: str | None = None


class DocumentsResponse(BaseModel):
    documents: list[DocumentVO] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class UploadResponse(BaseModel):
    document: DocumentVO
    chunks: int = 0


class DeleteResponse(BaseModel):
    deleted: bool = True


class RebuildResponse(BaseModel):
    documentCount: int = 0
    chunkCount: int = 0
    durationMs: int = 0
    mode: str = "mock"


# --------------------------------------------------------------------------
# AI1 /health
# --------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "UP"
    mode: str = "mock"
    knowledge_documents: int = 0
    knowledge_chunks: int = 0
    model: str = "deepseek-flash"
    llm_ready: bool = False
    # 契约 v1.1：向量索引信息
    vector_store: str = "InMemoryVectorStore"
    embedding: str = "LocalHashingEmbeddings"
    vector_dim: int = 1024
    vector_count: int = 0
    # 契约 v1.2 §3.2：embedding 双轨 + 混合检索能力声明
    embedding_provider: str = "local"
    embedding_model: str = "LocalHashingEmbeddings"
    embedding_dim: int = 1024
    retrieval_mode: str = "hybrid"
    supports_user_key: bool = True
    # 契约 v1.3 §1.2：图片识别能力（siliconflow | none）
    vision_provider: str = "none"
    vision_model: str = "Qwen/Qwen3-VL-8B-Instruct"
    vision_ready: bool = False


# --------------------------------------------------------------------------
# AI17 /vision/extract（v1.3）
# --------------------------------------------------------------------------
class VisionExtractResponse(BaseModel):
    """HTTP 恒为 200，用 ok 区分成功/失败（契约 §1.2）。"""

    ok: bool = False
    text: str = ""
    model: str = ""
    provider: str = "none"
    message: str | None = None
