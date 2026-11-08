# 个性化学习导师 · AI 服务（FastAPI）

高等数学考研辅导系统的 AI 能力层：知识库检索（RAG）+ 问答 + 诊断 + 练习 + 学习计划 + 班级分析 + 教师配置解析 + 图片识题 + 教师暂缓内容前置自测（gate）。对外契约见 `docs/开发过程/01-接口约定.md` 第 5 节（AI1~AI16），本服务不套统一响应外壳，成功直接返回业务 JSON，失败返回 HTTP 4xx/5xx + `{"detail":"..."}`。

- 技术栈：FastAPI + Pydantic v2 + httpx + python-dotenv；RAG 检索使用 **LangChain**（langchain-core 的 `Embeddings` 接口 + `InMemoryVectorStore` + langchain-text-splitters 递归分块）。默认用本地确定性哈希向量，**不依赖 jieba / 外部向量数据库 / 外部 embedding API**；也可通过 `EMBEDDING_PROVIDER=openai` 接入任意 OpenAI 兼容 embedding 服务（失败自动回退 local）。
- 说明：DeepSeek **没有** `/embeddings` 接口（实测 `POST /embeddings` 返回 404，`/models` 只有对话模型），因此 embedding 不能直接接 DeepSeek，v1.2 采用「检索增强 + 可插拔 embedding」双轨方案。
- v1.2 新增：多轮上下文（`history`/`conversationId`）、用户自带 key/模型（`llm`）、检索增强（查询归一化 + 同义扩展 + 混合打分 + chunkId 去重）、答案去内部编号、embedding provider 双轨（local/openai 回退）。
- v1.3 新增：图片识题 `POST /vision/extract`（硅基流动 OpenAI 兼容 vision 模型）、教师暂缓内容前置自测（`/qa` 返回 `gate` quiz，`POST /qa/gate/check` 判分并解锁三步教学）。DeepSeek 无 vision 接口，识图同样走外部 OpenAI 兼容服务，未配置 key 时接口仍返回 200 + 可操作提示。
- 端口：集成端口 **8000**（后端 Java 业务服务调用）；联调/自测可用 **8001** 避免与同事抢端口。
- 交互文档：启动后访问 `http://localhost:8000/docs`。

## 1. 目录结构

```
ai-service/
├─ app/
│  ├─ main.py          # 应用装配：日志、CORS、lifespan 启动重建索引、路由挂载
│  ├─ config.py        # .env 读取、AI_MODE、DeepSeek 参数、目录与检索参数、内置文档清单
│  ├─ schemas.py       # Pydantic 模型（字段名与契约完全一致）
│  ├─ knowledge.py     # 文档注册/分块/上传/启停/删除/重建/状态持久化
│  ├─ vector_store.py  # LangChain 向量检索：本地哈希 Embeddings + InMemoryVectorStore + 单元级 citation
│  ├─ embeddings.py    # 可插拔 embedding provider（local / openai 兼容），失败自动回退 local
│  ├─ query.py         # 查询归一化 + 规则同义扩展 + 术语权重，供混合检索使用
│  ├─ retrieval.py     # 旧版轻量检索（bigram + 权重），保留作对照
│  ├─ llm.py           # DeepSeek /chat/completions 调用、JSON 容错、重试与超时
│  ├─ vision.py        # 图片识题：OpenAI 兼容 vision 模型（默认硅基流动 Qwen3-VL）
│  ├─ gate.py          # 教师暂缓内容前置自测：题库选题、GateStore（TTL 2h）、判分
│  ├─ prompts.py       # 扣子 W1~W4 提示词迁移为模板（注入 teacherConfig/mastery/片段），v1.3 增 gate 教学
│  ├─ mock.py          # 确定性演示逻辑：全部 16 个接口的 mock 实现
│  ├─ rules.py         # 教学范围/禁用话题/回答模式等规则
│  ├─ kp.py            # 67 个知识点注册表（kp001~kp067）
│  ├─ builtin_questions.py  # 内置诊断题库（约 30 题，含 answerKey/analysis/errorType）
│  ├─ service.py       # 业务编排：mock 打底，real 模式覆盖 LLM 生成部分
│  └─ routers/
│     ├─ ai.py         # AI1~AI11 + v1.3 的 /vision/extract、/qa/gate/check
│     └─ knowledge.py  # AI12~AI16
├─ knowledge/
│  ├─ kb1_outline/     # KB1 课程大纲
│  ├─ kb2_textbook/    # KB2 教材讲义
│  ├─ kb3_questions/   # KB3 题库与解析
│  ├─ kb4_teacher/     # KB4 教师授权资料
│  ├─ kb5_graph/       # KB5 知识图谱（仅后台计算）
│  ├─ uploads/<classId>/  # 教师上传资料（按班级隔离）
│  └─ knowledge_points.json  # 67 个知识点（出题/报告使用）
├─ data/knowledge_state.json  # 文档启停状态持久化
├─ data/vector_index.json     # 向量索引清单（文档/分块/单元数/维度，供取证，不含向量本体）
├─ scripts/vector_demo.py     # 向量检索命令行演示（导入→重建→Top-K citation，截图用）
├─ tests/test_api.py   # unittest + TestClient 全接口自测（强制 mock，离线确定性）
├─ requirements.txt
└─ .env.example
```

## 2. 启动

在 `ai-service` 目录执行（Windows PowerShell）：

```powershell
# 1) 创建虚拟环境并安装依赖（首次）
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2) 启动（集成端口 8000；联调可用 8001）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动日志会打印运行模式与索引统计，例如：

```
INFO [ams.ai.vector] 向量索引重建完成：分块=60 检索单元=276 维度=1024 embedding=local 耗时=60ms
INFO [ams.ai.service] AI 服务就绪：mode=mock model=deepseek-flash llm_ready=False embedding=local/LocalHashingEmbeddings 文档=5 分块=60 向量=276 维度=1024 耗时=65ms
INFO [ams.ai] 启动完成：mode=mock model=deepseek-flash llm_ready=False documents=5 chunks=60 rebuild=65ms
```

真实模式（`.env` 已填 key）启动日志示例：

```
INFO [ams.ai.vector] 向量索引重建完成：分块=60 检索单元=276 维度=1024 embedding=local 耗时=105ms
INFO [ams.ai.service] AI 服务就绪：mode=real model=deepseek-flash llm_ready=True embedding=local/LocalHashingEmbeddings 文档=5 分块=60 向量=276 维度=1024 耗时=110ms
INFO [ams.ai] 启动完成：mode=real model=deepseek-flash llm_ready=True documents=5 chunks=60 rebuild=110ms
```

`GET /health` 实测（`AI_MODE=auto` 且 `.env` 已填 key）：

```json
{
  "status": "UP", "mode": "real", "model": "deepseek-flash", "llm_ready": true,
  "knowledge_documents": 5, "knowledge_chunks": 60,
  "vector_store": "InMemoryVectorStore",
  "embedding": "LocalHashingEmbeddings(char-ngram-1~3, blake2b-signed, dim=1024)",
  "vector_dim": 1024, "vector_count": 276,
  "embedding_provider": "local", "embedding_model": "LocalHashingEmbeddings", "embedding_dim": 1024,
  "retrieval_mode": "hybrid", "supports_user_key": true,
  "vision_provider": "siliconflow", "vision_model": "Qwen/Qwen3-VL-8B-Instruct", "vision_ready": true
}
```

> `vision_provider/vision_ready` 取决于 `VISION_API_KEY`（或回退 `EMBEDDING_API_KEY`）：未配置时分别为 `none` / `false`，图片接口仍返回 200 + 配置提示；`embedding_provider/embedding_model` 会显示实际生效的 embedding 服务（默认 `local`，配置 `EMBEDDING_PROVIDER=openai` 且探测成功时显示对应模型，如 `BAAI/bge-m3`）。

## 3. mock / real 模式

| AI_MODE | 行为 |
| --- | --- |
| `auto`（默认） | `DEEPSEEK_API_KEY` 有值 → real；无值 → mock。**未填 key 也能完整演示与验收** |
| `mock` | 强制离线演示：检索 + 规则 + 模板组织答案，不调用大模型 |
| `real` | 强制真实模式，缺少 key 时启动直接报错并提示填写方式 |

### 填写 DeepSeek Key（真实模式）

```powershell
cd ai-service
copy .env.example .env      # 已存在则跳过
# 编辑 .env，填写：
#   DEEPSEEK_API_KEY=sk-xxxxxxxx
#   AI_MODE=auto
```

- key 只放在 `ai-service/.env`，**不要提交到代码库或截图**；`.env` 不进版本管理。
- 修改 `.env` 后需**重启服务**生效（配置在启动时读取）。
- real 模式下任一 LLM 步骤失败（超时/断网/返回非 JSON）会自动降级为 mock 结果，并把响应里的 `mode` 标为 `mock`，接口不会 500。
- **图片识题另需 `VISION_API_KEY`**（硅基流动，见 `.env.example` 第 28~35 行），与 DeepSeek key 相互独立；未配置时只有 `/vision/extract` 返回 `ok=false` + 提示，其余接口不受影响。

## 4. 接口清单（AI1~AI16）

| 编号 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| AI1 | GET | `/health` | 健康检查：status/mode/model/llm_ready/knowledge_documents/knowledge_chunks/vector_store/embedding/vector_dim/vector_count + v1.2 的 embedding_provider/embedding_model/embedding_dim/retrieval_mode/supports_user_key + v1.3 的 vision_provider/vision_model/vision_ready |
| AI2 | POST | `/qa` | 学习问答：answer/sources/blocked/blockReason/intent/action/kpIds/knowledgeCovered/scopeWarning/mode；请求可带 history/conversationId/llm，响应带 model/modelSource/conversationId（v1.2） |
| AI3 | POST | `/intent` | 意图识别：intent/confidence/kpIds/reason |
| AI4 | POST | `/retrieve` | 知识检索：items/enough/topScore/mode |
| AI5 | POST | `/diagnose/questions` | 诊断出题：QUICK=5、FULL=15，难度 ≤ difficultyMax |
| AI6 | POST | `/diagnose/grade` | 诊断评分：results/score/level/errorSummary/advice |
| AI7 | POST | `/practice/questions` | 分层练习：A 难度1~2、B 2~3、C 3~4，只给 hint 不给答案 |
| AI8 | POST | `/practice/hint` | 递进提示：2~3 步，不泄露最终答案 |
| AI9 | POST | `/plan` | 学习计划：summary/days（goal/study/practiceQuestions/review） |
| AI10 | POST | `/class-analysis` | 班级分析：overview/weakTop10/errorSummary/hotQuestions/ranking/advice/summary |
| AI11 | POST | `/config/extract` | 教师自然语言配置解析：patch/explanation/unrecognized |
| AI12 | GET | `/knowledge/documents` | 文档列表与统计（可按 classId 过滤） |
| AI13 | POST | `/knowledge/upload` | 上传资料（multipart：file/kb/classId/uploadedBy） |
| AI14 | PATCH | `/knowledge/documents/{id}` | 启用/停用资料 |
| AI15 | DELETE | `/knowledge/documents/{id}` | 删除资料（内置资料禁止删除，返回 400） |
| AI16 | POST | `/knowledge/rebuild` | 重建索引：documentCount/chunkCount/durationMs/mode |
| v1.3 | POST | `/vision/extract` | 图片识题（multipart 字段 `file`，png/jpeg/webp/gif ≤5MB）：ok/text/model/provider/message；失败也返回 HTTP 200 |
| v1.3 | POST | `/qa/gate/check` | 前置自测判分：gateId/conversationId/answers → passed/score/total/state/feedback/answer/sources/knowledgeCovered/gate/teaching/mode/model/modelSource |
| v1.3 | POST | `/qa`（扩展） | 响应新增 `gate`（可为 null）；教师暂缓内容命中时返回 3 道前置单选 quiz，不调用大模型 |

## 5. 调用示例（PowerShell）

```powershell
$base = "http://localhost:8000"

# AI1 健康检查
Invoke-RestMethod -Uri "$base/health"

# AI2 学习问答（GUIDED/MIXED 引导式，不直接给最终答案；超范围返回 blocked=true）
$qa = @{ userId=1; role="STUDENT"; classId="C-GS-01"; message="洛必达法则的使用条件是什么" } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/qa" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($qa))

# AI2 多轮对话（v1.2：history 只取最近 8 条，响应回传 conversationId）
$qa2 = @{
  userId=1; role="STUDENT"; classId="C-GS-01"; conversationId="conv-1001"
  message="继续讲讲使用条件"
  history=@(
    @{role="user"; content="刚才讲到洛必达法则的适用条件"},
    @{role="assistant"; content="适用条件是 0/0 或 ∞/∞ 型"}
  )
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "$base/qa" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($qa2))

# AI2 使用学生自己的 key/模型（v1.2：仅本次请求有效，不写日志、不落库；失败自动降级系统 key 再降级 mock）
$qa3 = @{
  userId=1; role="STUDENT"; message="洛必达法则的使用条件是什么"
  llm=@{ apiKey="sk-你的key"; baseUrl="https://api.deepseek.com"; model="deepseek-flash" }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "$base/qa" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($qa3))

# AI5 诊断出题（QUICK 5 题，难度不超过 2）
$dq = @{ mode="QUICK"; count=5; difficultyMax=2; classId="C-GS-01" } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/diagnose/questions" -Method Post -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($dq))

# AI9 学习计划（7 天，结合薄弱知识点）
$plan = @{ period="WEEK"; days=7; goal="两周内突破极限与导数"; mastery=@(@{kpId="kp021"; kpName="洛必达法则"; mastery=35}) } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "$base/plan" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($plan))

# AI10 班级分析
$ca = @{ period="7D"; classId="C-GS-01"; studentCount=30; totalInteractions=120; activeStudents=20; accuracy=0.62 } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/class-analysis" -Method Post -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($ca))

# AI11 教师配置解析
$ce = @{ text="把最大难度调到2，暂时关闭教师资料，级数先别讲" } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/config/extract" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($ce))

# AI12 文档列表
Invoke-RestMethod -Uri "$base/knowledge/documents"

# AI13 上传教师资料（KB4，班级隔离）
Invoke-RestMethod -Uri "$base/knowledge/upload" -Method Post -Form @{
  file = Get-Item ".\knowledge\kb4_teacher\高等数学教师授权资料-知识库版.md"
  kb = "KB4"; classId = "C-GS-01"; uploadedBy = "1"
}

# AI16 重建索引
Invoke-RestMethod -Uri "$base/knowledge/rebuild" -Method Post

# v1.3 图片识题（PowerShell 5.1 无 -Form，用 curl.exe 发 multipart；未配置 key 时 ok=false）
curl.exe -s -X POST "$base/vision/extract" -F "file=@D:\path\题目.png"

# v1.3 教师暂缓内容：/qa 返回 3 道前置单选（不含 answerKey，不调用大模型）
$gateReq = @{
  userId=1; role="STUDENT"; classId="C-GS-01"; conversationId="conv-gate-1"
  message="级数怎么判断收敛？"
  teacherConfig=@{ answerMode="MIXED"; maxDifficulty=3; disabledTopics=@("级数") }
} | ConvertTo-Json -Depth 6
$quiz = Invoke-RestMethod -Uri "$base/qa" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($gateReq))
$quiz.gate.questions    # 3 道单选题（questionId/index/kpId/stem/options），答案只在服务端 GateStore

# v1.3 提交前置测试：通过线 2/3；FAILED 不生成教学答案，PASSED 返回三步 teaching 并解锁该话题
$gateCheck = @{
  gateId=$quiz.gate.gateId; conversationId="conv-gate-1"
  answers=@(@{questionId="gq1";choice="A"},@{questionId="gq2";choice="B"},@{questionId="gq3";choice="C"})
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri "$base/qa/gate/check" -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($gateCheck))
```

> 中文请求体请使用 `[Text.Encoding]::UTF8.GetBytes(...)` 或 `-ContentType "application/json; charset=utf-8"`，避免 PowerShell 以 GBK 发送导致乱码。

## 6. 知识库与检索（RAG）

- **内置 5 类资料**（scope=GLOBAL，所有班级可见，开机自动加载）：
  - KB1 `kb1_outline/` 课程大纲；KB2 `kb2_textbook/` 教材讲义；KB3 `kb3_questions/` 题库与解析；KB4 `kb4_teacher/` 教师授权资料；KB5 `kb5_graph/` 知识图谱（仅后台计算，不直接对外展示）。
- **上传资料**：保存在 `knowledge/uploads/<classId>/`，scope=CLASS，仅该班级可见；教师可在前端上传/停用/删除。
- **两级切分（v1.2 增加知识点对齐）**：
  1. 文档级分块：按标题/段落切分，块长 600~800 字、重叠约 100 字（`knowledge.py`）；
  2. 向量检索单元：先按行首 `kpNNN` 把分块对齐到知识点，再用 `RecursiveCharacterTextSplitter`（chunk_size=420、overlap=60）切成 ≤420 字的检索单元，保证一个单元只对应一个知识点，引用不会跨章节错位（此前「定积分的几何意义」错引到第4节的问题即由此修复）。
- **向量索引**：默认 `LocalHashingEmbeddings`（字符 1~3-gram + blake2b 有符号哈希，1024 维、L2 归一，离线、确定性）→ LangChain `InMemoryVectorStore`；启动与上传/启停/删除/重建后自动重建，索引清单写入 `data/vector_index.json`（分块数、单元数、维度、文档清单，不含向量本体）。
- **检索增强（v1.2 §1 A 轨）**：查询先做归一化（全半角、数学符号）与规则同义扩展（如「分部积分」→「分部积分法/凑微分/反对幂指三」）；real 模式下再用 DeepSeek 改写查询词（失败自动回退规则扩展）。改写词只做「扩展召回」：原问题检索结果优先，改写结果只补充新命中，避免「不定积分」等词把原问题的 top1 顶到相邻章节。
- **多轮追问检索（v1.2 联调修复）**：请求带 `history` 且当前问题很短（≤12 字）或命中「再来一个/难一点/继续/下一题/换一个/…」时，检索 query = 当前问题 + 最近一条 user 历史；历史只参与检索，不进入 `sources`/`citation`。检索采用混合打分：`0.55 × 余弦相似度 + 0.45 × 词法命中率`，再乘知识库优先级（KB2 1.0 > KB1 0.97 > KB3 0.93 > KB4 0.90 > KB5 0.86），并对主知识点/知识点名命中加权。
- **sources 去重**：同一 `chunkId` 只保留得分最高的检索单元，`sources` 数量与实际入库片段一一对应，最多 `topK=8`；低于阈值时返回 `enough=false, items=[]`；阈值随 embedding 方案切换（v1.2 实测校准）：本地哈希用 `RETRIEVAL_MIN_SCORE=0.15`，语义 embedding（如 `BAAI/bge-m3`）用 `EMBEDDING_MIN_SCORE=0.40`（语义模型对无关问题的分数基线明显更高，实测天气 0.28 / 英语 0.28 / 矩阵 0.39，相关高数问题 0.70~0.99）。
- **可插拔 embedding（v1.2 §1 B 轨）**：`EMBEDDING_PROVIDER=local|openai`，`EMBEDDING_BASE_URL/EMBEDDING_API_KEY/EMBEDDING_MODEL` 指向任意 OpenAI 兼容 `/embeddings` 服务；缺 key、探测失败或维度异常时自动回退 local，`/health` 的 `embedding_provider` 始终是实际生效值。
- **引用（citation）**：每条命中带 `chapter/section/citation`，形如「《高等数学教材讲义》第3章·第3节 洛必达法则」，回答末尾汇总为【参考资料】，学生可回看原文。
- **答案清理（v1.2 §3.3，硬性）**：提示词禁止模型输出「片段 N」「chunk N」「kpNNN」「documentId」；若模型仍输出，服务层会把「片段 N」替换为对应 citation（无法定位时用「知识库相关章节」）、`kpNNN` 替换为知识点中文名，保证前端只看到可读引用。
- **行为矩阵（契约 v1.1 / v1.2）**：

  | 场景 | blocked | knowledgeCovered | scopeWarning | sources |
  | --- | --- | --- | --- | --- |
  | 超纲科目（线代/矩阵/概率/物理/复变/数分/离散等） | true | false | null | `[]`，answer=统一话术「该内容超出当前教学范围，暂时无法解答。」；响应 `mode` 为服务实际模式（real/mock）、`modelSource=none`（规则拦截，未调用模型） |
  | 教师暂缓内容（disabledTopics / 教学范围外 / boundaryRules，v1.3） | false | false | null | `[]`，answer=gate 说明文案，`action={type:"GATE",label:"前置自测"}`，响应含 `gate`（3 道前置单选，不含答案）；不调用大模型 |
  | 前置自测已通过后再问同话题（v1.3） | false | 按检索结果 | null | 正常检索答疑（不再出 gate，可能为空） |
  | 非数学话题（英语/政治/编程/生活） | false | false | 固定提醒 | `[]`，answer 仍给出有帮助的通用建议 |
  | 数学范围内但知识库无命中 | false | false | null | `[]`，answer 含「知识库暂无相关内容」「换一种问法」 |
  | 命中知识库 | false | true | null | 带 citation 的片段（chunkId 去重），answer 末尾【参考资料】 |
- **状态持久化**：文档启停写入 `data/knowledge_state.json`，重启后保留；内置资料可停用但不可删除（删除返回 400）。
- **重建索引**：`POST /knowledge/rebuild` 重新读取全部资料并重建分块与向量索引，响应含耗时；启动时（lifespan）也会自动重建一次。

### 教师暂缓内容前置自测（v1.3 gate）

- **判定顺序**：硬拦截（HARD/UNETHICAL）→ 教师配置命中（`disabledTopics` / `effectiveKpIds` 教学范围外 / `boundaryRules`）→ 软范围 → 检索答疑。
- **gate quiz**：命中教师暂缓内容且该 `(conversationId, topic)` 尚未通过时，`/qa` 返回 `gate`：3 道单选（题源 `builtin_questions` 中带 `options`+`answerKey`、`difficulty≤2` 的题；优先取主题知识点之前的 kp，排除主题自身），`action={type:"GATE",label:"前置自测"}`，`blocked=false`、`sources=[]`、`knowledgeCovered=false`。**答案只存服务端 GateStore（按 gateId，TTL 2 小时），响应绝不含 `answerKey`/`analysis`**，且此分支不调用大模型（响应快，约 30ms）。
- **判分 `POST /qa/gate/check`**：通过线 2/3（允许错 1 题）。`FAILED` 不生成教学答案（`answer=""`、`sources=[]`、`knowledgeCovered=false`），`feedback` 指出薄弱前置 kp；`PASSED` 返回三步教学 `teaching.steps`（mock 模板必含「第 1 步/第 2 步/第 3 步」；real 调 DeepSeek 生成，失败自动降级 mock 并把响应 `mode` 标为 `mock`），并记录 `(conversationId, topic)` 通过状态，后续同会话再问该话题直接正常答疑（不再出 gate）。
- **过期/异常**：`gateId` 不存在或超过 TTL → HTTP 200 + `state="EXPIRED"` 固定结构（`total=0`、`feedback="前置测试已过期，请重新提问。"`）；矩阵等硬拦截仍走 `blocked=true`，不产生 gate。
- **离线可用**：mock 模式题库与判分全部本地完成，无需任何 key。

### 图片识题（v1.3 `/vision/extract`）

- **模型分离**：DeepSeek 无 vision 接口，图片识别走 OpenAI 兼容的视觉模型（默认硅基流动 `Qwen/Qwen3-VL-8B-Instruct`）；配置 `VISION_PROVIDER=auto`（默认）+ `VISION_API_KEY`（留空时回退 `EMBEDDING_API_KEY`），可用 `VISION_BASE_URL/VISION_MODEL/VISION_TIMEOUT_SECONDS` 覆盖。
- **接口**：multipart 字段 `file`，允许 png/jpeg/jpg/webp/gif、≤5MB；AI 侧不做缩放（前端负责压缩），直接 base64 data URL 转发。响应 `{ok,text,model,provider,message}`，**失败也返回 HTTP 200**，用 `ok` 区分。
- **失败文案**：未配置 key → `ok=false` + 「未配置识图模型：请在 ai-service/.env 配置 VISION_API_KEY（或复用 EMBEDDING_API_KEY）后重启服务。」；非 png/jpeg/webp/gif → 「仅支持 png/jpeg/webp/gif 格式的图片。」；超时/报错 → 「图片识别失败，请重试或改为文字输入。」
- **识别约束**：提示词要求原样输出题干与公式（LaTeX），不解答、不补充、看不清标 `[不清]`；识别文本由前端填入输入框，再走 `/qa` 正常答疑链路。

## 7. 自测

```powershell
cd ai-service
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# 向量检索演示（打印文档数 / 分块数 / 向量维度 / Top-K citation）
.\.venv\Scripts\python.exe scripts\vector_demo.py
```

实测结果（测试在导入 app 前强制 `AI_MODE=mock`，离线、确定性运行，不读取/打印 .env 中的 key）：

```
Ran 55 tests in 3.9s

OK
```

覆盖 AI1~AI16 + v1.3 的 `/vision/extract`、`/qa/gate/check` 全部接口、4 个验收场景、契约 v1.1/v1.2/v1.3 行为矩阵与真实模式容错：

1. 知识库无相关内容：`/retrieve` 返回 `enough=false`、`items=[]`；数学问题无命中时 `/qa` 明确说明「知识库暂无相关内容」并建议「换一种问法」。
2. 超范围问题：线代/矩阵/概率/复变等 `/qa` 返回 `blocked=true` 与统一话术；英语/政治/编程/生活等软范围返回 `blocked=false` + `scopeWarning`。
3. 作业/考试题：`/qa` 输出五段引导（【先判断】【思路引导】【知识点讲解】【易错提醒】【下一步】），拒绝直接给最终答案。
4. 难度过滤：`/diagnose/questions difficultyMax=2` 返回题目难度全部 ≤ 2；`/practice/questions` 分层难度符合 A/B/C 区间。
5. 检索与引用：命中片段带 `citation`（如「《高等数学教材讲义》第3章·第3节 洛必达法则」）；上传的班级资料进入向量索引，且其他班级检索不到。
6. 容错：模型输出 JSON 清洗（裸 JSON / markdown 代码块 / 前后缀）可解析；LLM 调用失败自动降级 mock，响应 200 且 `mode=mock`。
7. 检索召回（v1.2 §2）：`求∫2xe^xdx` 能召回到「第4章·第4节 分部积分法」（kp031/kp035），不再错落到微分方程章节；7 条检索验收用例全部通过。
8. 引用去重与答案清理（v1.2 §2/§3.3）：`sources` 按 `chunkId` 去重；模型输出中的「片段 N」「chunk N」「kpNNN」会被替换为 citation/知识点中文名，答案不暴露内部编号。
9. 多轮与用户 key（v1.2 §3.1）：`history` 只取最近 8 条（≤4000 字符）注入提示词，`conversationId` 原样回传；请求级 `llm` 覆盖优先使用用户 key，日志与响应均不泄露 key。
10. embedding 双轨（v1.2 §1）：`EMBEDDING_PROVIDER=openai` 缺配置时自动回退 local，`/health.embedding_provider` 反映实际生效值。
11. 追问检索（v1.2 联调）：第一问求 ∫2xe^xdx，第二问「你再来一个难一点的」+ history → `knowledgeCovered=true`、`sources[0].citation` 为「第4章·第4节 分部积分法」，且追问原句不会出现在 citation 中。
12. 硬拦截模式（v1.2 联调）：real 模式下矩阵问题返回 `blocked=true`、`mode=real`、`modelSource=none`、`answer` 为统一话术。
13. 教师暂缓内容 gate（v1.3）：`disabledTopics=["级数"]` 触发 `/qa` gate quiz（3 题、`blocked=false`、`sources=[]`、`action.type=GATE`、无 `answerKey`）；全错 → `FAILED` 且无教学答案、不调 LLM；全对 → `PASSED` + 三步教学（含「第 1 步/第 2 步/第 3 步」）+ `sources` 非空；通过后同会话再问不再出 gate；`gateId` 不存在 → `EXPIRED` 固定结构；矩阵仍硬拦截且无 gate。
14. 图片识题（v1.3）：未配置 key → HTTP 200 + `ok=false` + 配置提示；识图成功/失败（monkeypatch vision client）分别返回 `ok=true` 文本与 `ok=false` 失败文案；`/health` 的 `vision_provider/vision_model/vision_ready` 与实际配置一致；gate 教学 real 成功时 `mode=real/modelSource=system`，失败降级 mock 仍保证三步标题。

## 8. 常见问题

- **填了 key 仍是 mock**：检查 `ai-service/.env` 是否存在、`DEEPSEEK_API_KEY` 是否非空、是否重启服务；`/health` 的 `llm_ready` 为 `false` 即未生效。
- **想用自己的 API key / 模型**：前端把 `llm: {apiKey, baseUrl, model}` 放进 `/qa` 请求体即可，仅本次请求生效；失败会先降级系统 key、再降级 mock，响应 `modelSource` 标识实际来源（`user`/`system`/`mock`）；规则硬拦截（超纲科目）不调用模型，返回 `modelSource=none` 且 `mode` 为服务实际模式。
- **Embedding 能不能直接接 DeepSeek**：不能，DeepSeek 没有 `/embeddings` 接口（404）。默认用本地哈希向量即可离线演示；如需语义 embedding，配置 `EMBEDDING_PROVIDER=openai` + 任意 OpenAI 兼容服务（如 BGE-M3）。
- **real 模式启动报错**：`AI_MODE=real` 但无 key。改为 `auto`，或填写 key。
- **图片识题不可用（ok=false）**：检查 `ai-service/.env` 的 `VISION_API_KEY`（或回退的 `EMBEDDING_API_KEY`）是否非空、`VISION_PROVIDER` 是否为 `none`，并重启服务；`/health` 的 `vision_ready` 为 `false` 即未生效。`/vision/extract` 失败也返回 HTTP 200，请按 `ok`/`message` 判断。
- **教师暂缓内容为什么不直接答**：教师配置了 `disabledTopics` / 教学范围 / `boundaryRules` 时，`/qa` 会先出 3 道前置自测（gate），通过线 2/3；前端应渲染 `gate` 卡片并提交到 `/qa/gate/check`。`answerKey` 只在服务端，接口不返回。
- **gate 提交报 EXPIRED**：`gateId` 超过 2 小时或服务重启后失效，重新提问即可获得新 gate。
- **上传接口 422**：multipart 字段名必须是 `file`，表单字段 `kb`/`classId`/`uploadedBy`。
- **删除内置资料 400**：内置 5 份资料只允许停用（PATCH enabled=false），不允许删除。
- **中文乱码**：请求头带 `charset=utf-8`，并用 UTF-8 字节发送 body。