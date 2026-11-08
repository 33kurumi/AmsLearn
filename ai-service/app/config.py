"""集中配置：读取 ai-service/.env，确定运行模式、DeepSeek 参数、知识库目录与检索参数。

约定（见 docs/01-接口约定.md 第 7 节）：
- AI_MODE=auto：填写 DEEPSEEK_API_KEY 即真实模型，否则 mock；
- AI_MODE=mock：强制 mock；AI_MODE=real：强制真实（无 key 启动即报错）。
"""
from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent  # ai-service 目录


def _load_dotenv() -> None:
    """加载 ai-service/.env；python-dotenv 缺失时静默降级为系统环境变量。"""
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - 依赖缺失时仍可运行
        return
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


_load_dotenv()


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env_str(name, str(default)) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)) or default)
    except ValueError:
        return default


class Settings:
    """全局配置对象。所有路径均可通过环境变量覆盖，便于测试隔离。"""

    def __init__(self) -> None:
        self.app_name = "AmsLearn 个性化学习导师 AI 服务"
        self.version = "1.0.0"

        # ---- 运行模式与模型 ----
        self.ai_mode = (_env_str("AI_MODE", "auto") or "auto").lower()
        if self.ai_mode not in {"auto", "mock", "real"}:
            self.ai_mode = "auto"
        self.deepseek_api_key = _env_str("DEEPSEEK_API_KEY", "")
        self.deepseek_model = _env_str("DEEPSEEK_MODEL", "deepseek-flash") or "deepseek-flash"
        self.deepseek_base_url = (_env_str("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com").rstrip("/")
        self.llm_timeout_seconds = _env_float("LLM_TIMEOUT_SECONDS", 90.0)
        self.llm_retries = _env_int("LLM_RETRIES", 2)

        # ---- 目录 ----
        self.knowledge_dir = Path(_env_str("AI_KNOWLEDGE_DIR", str(BASE_DIR / "knowledge")))
        self.data_dir = Path(_env_str("AI_DATA_DIR", str(BASE_DIR / "data")))
        self.upload_dir = Path(_env_str("AI_UPLOAD_DIR", str(self.knowledge_dir / "uploads")))
        self.state_file = Path(_env_str("AI_KNOWLEDGE_STATE", str(self.data_dir / "knowledge_state.json")))
        # v1.4.1：前置自测（gate）会话状态持久化到 SQLite，服务重启后仍可续做/不再重复出题
        self.gate_db_file = Path(_env_str("AI_GATE_DB", str(self.data_dir / "gate.db")))
        self.kp_file = Path(_env_str("AI_KP_FILE", str(self.knowledge_dir / "knowledge_points.json")))

        # ---- 检索与分块参数（PRD 4.2 / 任务书 B）----
        self.chunk_min_chars = _env_int("CHUNK_MIN_CHARS", 600)
        self.chunk_max_chars = _env_int("CHUNK_MAX_CHARS", 800)
        self.chunk_overlap_chars = _env_int("CHUNK_OVERLAP_CHARS", 100)
        self.top_k = _env_int("RETRIEVAL_TOP_K", 8)
        self.min_score = _env_float("RETRIEVAL_MIN_SCORE", 0.15)
        self.upload_max_bytes = _env_int("UPLOAD_MAX_BYTES", 2 * 1024 * 1024)

        # ---- v1.2 检索增强：可插拔 embedding provider 与查询扩展（契约 3.5）----
        # DeepSeek 没有 embeddings 接口（/embeddings 404），因此默认使用本地哈希向量；
        # 用户若另有 OpenAI 兼容 embedding 服务，可切换 provider=openai 并配置下面四项。
        self.embedding_provider = (_env_str("EMBEDDING_PROVIDER", "local") or "local").lower()
        if self.embedding_provider not in {"local", "openai"}:
            self.embedding_provider = "local"
        self.embedding_base_url = (
            _env_str("EMBEDDING_BASE_URL", "") or ""
        ).rstrip("/")
        self.embedding_api_key = _env_str("EMBEDDING_API_KEY", "")
        self.embedding_model = _env_str("EMBEDDING_MODEL", "")
        self.embedding_timeout_seconds = _env_float("EMBEDDING_TIMEOUT_SECONDS", 30.0)
        # 「知识库是否覆盖」的相似度阈值。本地哈希向量与远程语义向量的分数分布差异很大：
        # bge-m3 这类语义模型对「今天天气怎么样」也会给到 0.28~0.39，沿用 0.15 会把闲聊
        # 误判成「知识库已覆盖」，因此按 provider 分别取阈值（见 effective_min_score）。
        self.embedding_min_score = _env_float("EMBEDDING_MIN_SCORE", 0.40)
        # ---- v1.3 图片识别（契约 §1.1）：DeepSeek 无 vision，转发硅基流动 Qwen3-VL ----
        # VISION_PROVIDER=auto：VISION_API_KEY 非空（或回退 EMBEDDING_API_KEY）即启用；
        # none：关闭识图；siliconflow：强制认为已配置（缺 key 时调用失败并返回 ok=false）。
        self.vision_provider = (_env_str("VISION_PROVIDER", "auto") or "auto").lower()
        if self.vision_provider not in {"auto", "siliconflow", "none"}:
            self.vision_provider = "auto"
        self.vision_base_url = (
            _env_str("VISION_BASE_URL", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"
        ).rstrip("/")
        self.vision_api_key = _env_str("VISION_API_KEY", "")
        self.vision_model = _env_str("VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct") or "Qwen/Qwen3-VL-8B-Instruct"
        self.vision_timeout_seconds = _env_float("VISION_TIMEOUT_SECONDS", 60.0)

        # auto：real 模式用 DeepSeek 改写查询词；off：只用本地规则扩展
        self.query_expansion = (_env_str("QUERY_EXPANSION", "auto") or "auto").lower()
        if self.query_expansion not in {"auto", "off"}:
            self.query_expansion = "auto"

        # ---- 允许跨域（本服务内网调用，仅便于本地调试）----
        self.cors_origins = [
            origin.strip()
            for origin in _env_str("AI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080").split(",")
            if origin.strip()
        ]

    # ---- 派生属性 ----
    def effective_min_score(self, provider: str | None = None) -> float:
        """当前 embedding 方案下「知识库命中」的相似度阈值。

        本地哈希向量：无关问题分数接近 0，沿用 RETRIEVAL_MIN_SCORE（默认 0.15）；
        远程语义向量（provider=openai）：无关问题基线 0.28~0.39、相关问题 0.70~0.99，
        用 EMBEDDING_MIN_SCORE（默认 0.40）避免把闲聊误判为「知识库已覆盖」。
        """
        current = (provider or self.embedding_provider or "local").lower()
        return self.embedding_min_score if current == "openai" else self.min_score

    @property
    def mode(self) -> str:
        """最终生效模式：mock / real。"""
        if self.ai_mode == "real":
            return "real"
        if self.ai_mode == "mock":
            return "mock"
        return "real" if self.deepseek_api_key else "mock"

    @property
    def llm_ready(self) -> bool:
        return self.mode == "real" and bool(self.deepseek_api_key)

    @property
    def chat_completions_url(self) -> str:
        return f"{self.deepseek_base_url}/chat/completions"

    # ---- v1.3 识图（契约 §1.1）----
    @property
    def resolved_vision_api_key(self) -> str:
        """VISION_API_KEY 为空时回退硅基流动 EMBEDDING_API_KEY（同一平台可复用）。"""
        return self.vision_api_key or self.embedding_api_key

    @property
    def vision_ready(self) -> bool:
        """auto/siliconflow 且有可用 key 才算就绪；none 恒为 False。"""
        if self.vision_provider == "none":
            return False
        return bool(self.resolved_vision_api_key)

    @property
    def vision_provider_name(self) -> str:
        """Health 暴露的 provider 名：siliconflow | none。"""
        return "siliconflow" if self.vision_ready else "none"

    @property
    def vision_chat_completions_url(self) -> str:
        base = self.vision_base_url or "https://api.siliconflow.cn/v1"
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def validate(self) -> None:
        """启动校验：real 模式必须有 key，目录必须存在。"""
        if self.ai_mode == "real" and not self.deepseek_api_key:
            raise RuntimeError(
                "AI_MODE=real 但未读取到 DEEPSEEK_API_KEY，请在 ai-service/.env 中填写 key，"
                "或将 AI_MODE 改为 auto/mock。"
            )
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def supports_user_key(self) -> bool:
        """v1.2：/qa 支持请求级 llm 覆盖（用户自己的 key），默认走系统 key。"""
        return True

    def describe(self) -> str:
        return (
            f"mode={self.mode} (AI_MODE={self.ai_mode}, key={'已配置' if self.deepseek_api_key else '未配置'}), "
            f"model={self.deepseek_model}, timeout={self.llm_timeout_seconds:g}s, "
            f"embedding={self.embedding_provider}"
        )


# 内置 5 份知识库资料（GLOBAL，所有班级可见）。KB5 仅后台计算，不对外暴露。
SEED_DOCUMENTS = [
    {
        "documentId": "kb1-outline",
        "kb": "KB1",
        "dir": "kb1_outline",
        "name": "高等数学课程大纲-知识库版.md",
        "title": "高等数学课程大纲",
    },
    {
        "documentId": "kb2-textbook",
        "kb": "KB2",
        "dir": "kb2_textbook",
        "name": "高等数学教材讲义-知识库版.md",
        "title": "高等数学教材讲义",
    },
    {
        "documentId": "kb3-questions",
        "kb": "KB3",
        "dir": "kb3_questions",
        "name": "高等数学题库-知识库版.md",
        "title": "高等数学题库与解析",
    },
    {
        "documentId": "kb4-teacher",
        "kb": "KB4",
        "dir": "kb4_teacher",
        "name": "高等数学教师授权资料-知识库版.md",
        "title": "高等数学教师授权资料",
    },
    {
        "documentId": "kb5-graph",
        "kb": "KB5",
        "dir": "kb5_graph",
        "name": "高等数学知识图谱-知识库版.md",
        "title": "高等数学知识图谱",
    },
]

KB_TITLES = {item["kb"]: item["title"] for item in SEED_DOCUMENTS}

# KB 召回优先级：教材 > 大纲 > 题库 > 教师资料 > 图谱（PRD 4.2）
KB_PRIORITY = {"KB2": 1.0, "KB1": 0.97, "KB3": 0.93, "KB4": 0.90, "KB5": 0.86}

settings = Settings()
