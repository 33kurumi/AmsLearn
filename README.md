# 个性化学习导师（高等数学考研辅导）

面向考研学生与高数任课教师的**全栈个性化学习系统**：教师为班级设定难度/知识范围/回答边界，学生在边界内获得知识库答疑、薄弱点诊断、分层练习与学习计划；教师端查看班级学情。核心产品特征：**教师配置即时生效 + 学生侧引导式（作业题只给思路，不直接给最终答案）**。

课程实训全量实现项目，三端分离、契约冻结（`docs/开发过程/01-接口约定.md`）。

> **当前版本 v1.4.1（2026-11-08，real 模式已三端实测）**：前置自测 gate 状态由进程内存改为 **SQLite 持久化**，AI 重启后未过期的自测仍可继续作答；三端验收 **24/24 PASS**。各版本加了什么、当前实测指标，见 [§10 项目状态](#10-项目状态与团队)。

## 1. 项目总览

| 端 | 技术 | 端口 | 职责 |
| --- | --- | --- | --- |
| 前端 | Vue 3 + Vite 6 + KaTeX | 5173 | 登录、学生 8 页、教师 6 页、公式渲染、交互提示 |
| 业务服务 | Spring Boot 3 + JPA + H2 | 8080 | 鉴权、10 表读写、学生/教师接口、编排 AI、种子数据 |
| AI 服务 | FastAPI + LangChain 混合检索（KB1~KB5，Embedding 双轨 local/openai）；v1.3 新增图片转文字（视觉模型）与前置自测 gate | 8000 |
| LLM | DeepSeek（`deepseek-flash`，可配 `deepseek-v4-pro`）；答案生成 | — |
| 视觉模型（v1.3） | 硅基流动 OpenAI 兼容 `Qwen/Qwen3-VL-8B-Instruct`（可选 32B），仅用于图片转文字 | — |

```text
浏览器(5173)
   │  /api/*（Bearer Token，统一响应）
   ▼
Spring Boot(8080) ── 10 张表（H2 文件库）── 实时读班级配置（不缓存 → 改完立即生效）
   │  HTTP /ai/*（AI1~AI16）
   ▼
FastAPI(8000) ── KB1~KB5 + 67 知识点 ── LangChain 混合检索（向量+关键词，本地 Embeddings；可选 openai embedding）
   │  ├─ 答疑/诊断/练习/计划 → DeepSeek（有 key 默认 real，无 key mock；用户可自带 Key）
   │  └─ 图片转文字（v1.3）→ 硅基流动 Qwen3-VL-8B（仅识别文字，不解答）
```

功能闭环：教师配置 → 答疑/诊断 → 掌握度与错题 → 计划/分层练习 → 班级学情分析。

## 2. 快速开始（5 步）

> 本节命令与相对路径均以**项目根目录**（即含 `README.md` 的 `AmsLearn` 文件夹）为基准；项目可放在任意盘位/路径，只要进到这个目录再执行。

1. **检查环境**：双击 `scripts/检查环境.bat`（Node 22 / JDK 17 / Maven Wrapper / Python 3.12 / 端口 5173/8080/8000）。
2. **配置 AI（推荐，填 key 即默认 real）**：复制 `ai-service/.env.example` 为 `ai-service/.env`，把 DeepSeek key 写入 `DEEPSEEK_API_KEY=sk-...`，保持 `AI_MODE=auto`（有 key 走真实 DeepSeek，无 key 自动降级 mock，均不影响演示）。**key 只放这一处**，Java 与前端都不需要；改完重启 AI 服务，用 <http://localhost:8000/health> 的 `mode`/`vector_*` 字段确认。依赖安装见下。
3. **启动三端**：双击 `scripts/启动全部服务.bat`（顺序 AI 8000 → Java 8080 → 前端 5173）；或分别运行 `启动AI服务.bat`、`启动Java服务.bat`、`启动Vue前端.bat`。
4. **打开页面**：<http://localhost:5173>，用演示账号登录（见 §4）。健康检查：<http://localhost:8000/health>、<http://localhost:8080/api/health>。
5. **跑验收**：三端启动后执行 `ai-service\.venv\Scripts\python.exe scripts\acceptance_check.py`，输出 PASS/FAIL/SKIP 表与退出码（0 全 PASS / 1 有 FAIL / 3 有 SKIP）；总 **24 项** = v1.2 基线 20 项 + v1.3 新增 C-16/C-16b/C-21 + v1.4 新增 C-22（自助注册）/C-23（教师重置密码）。

> **v1.3 图片识别（可选）**：`ai-service/.env` 增 `VISION_PROVIDER=auto`（默认，有 key 即启用）、`VISION_BASE_URL=https://api.siliconflow.cn/v1`、`VISION_API_KEY=`（**留空自动复用 `EMBEDDING_API_KEY`**，两者都没有则图片按钮提示改用文字输入，不影响文字答疑与验收）。`/health` 的 `vision_ready` 可确认是否就绪。

手动安装 AI 依赖（**以下命令在项目根目录执行**；受限环境实测命令，避免 pip 缓存卡死）：

```bat
cd ai-service
python -m venv .venv
.venv\Scripts\python.exe -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
```

v1.1 依赖已加入 `requirements.txt`：`langchain-core 1.7.6`、`langchain-text-splitters 1.1.3`、`numpy`（本地 Embeddings 与 InMemoryVectorStore），无需外部 embedding 服务。
v1.2 无需新增依赖（`EMBEDDING_PROVIDER=openai` 仅用 httpx 调 OpenAI 兼容接口，缺 key 自动回退 local）；如需多轮会话与用户 Key，只需启动三端后按 §3 配置即可，无需额外安装。

前端：`cd frontend && set npm_config_cache=..\.npm-cache && npm install && npm run dev`（`..\.npm-cache` 即项目根目录下的缓存目录）。

## 3. DeepSeek Key 放在哪里

- 文件：`ai-service/.env`（由 `.env.example` 复制，**不提交、不截图**）
- 键名：`DEEPSEEK_API_KEY=sk-...`；可选 `DEEPSEEK_MODEL=deepseek-flash`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`LLM_TIMEOUT_SECONDS=90`；v1.2 可选 `EMBEDDING_PROVIDER=local|openai`、`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`、`QUERY_EXPANSION=auto|off`
- 模式：`AI_MODE=auto`（默认，**有 key 走真实 `mode=real`**，无 key 自动降级 `mock`）/ `real` / `mock`；改后重启 AI 服务，`/health` 的 `mode`、`vector_store`、`vector_count` 字段可确认
- **v1.3 图片识别 key**：`VISION_API_KEY`（硅基流动）；留空则复用 `EMBEDDING_API_KEY`；`VISION_PROVIDER=none` 可关闭识图。DeepSeek 的 key **不能**用于识图（DeepSeek 无图像输入）。
- 其他位置都不需要 key：Java 与前端只调本机 AI 服务。
- **v1.2 用户自带 Key（可选）**：学生/教师登录后可在「个人信息 → AI 模型设置」填自己的 DeepSeek Key/Base URL/模型；Key 由 Java 用 AES/GCM 加密存本机数据库，接口只回掩码 `sk-***abcd`，不写日志。留空则用系统 Key（`ai-service/.env`）。顶栏徽标显示当前是 `real · 模型 · 系统 Key`、`real · 我的 Key` 还是 `mock`。

## 4. 演示账号

| 角色 | 账号 | 密码 | 班级 |
| --- | --- | --- | --- |
| 教师 | `teacher1` | `123456` | C-GS-01 考研高数强化班（王老师） |
| 教师 | `teacher2` | `123456` | C-GS-02 考研高数基础班（李老师） |
| 学生 | `student1`~`student3` | `123456` | C-GS-01（张/李/王同学） |
| 学生 | `student4`~`student5` | `123456` | C-GS-02（赵/陈同学） |

## 5. 目录说明

```text
AmsLearn/
├─ frontend/                Vue3 + Vite 6（5173，访问必须用 http://localhost:5173）
│  ├─ src/views/student/    学生 8 页：首页 / 答疑辅导 / 知识诊断 / 学习计划 / 分层练习 / 学习记录 / 错题复盘 / 个人信息
│  ├─ src/views/teacher/    教师 6 页：学情总览 / 班级配置 / 知识库管理 / 学生记录 / 班级学情 / 个人信息
│  ├─ src/views/LoginView.vue  登录 + 学生自助注册
│  ├─ src/components/       通用组件：MarkdownView、MasteryBars、GateCard、AiModelSettings、Toast/Skeleton/Empty/Error
│  ├─ src/api.js            统一请求封装（Bearer Token + 统一响应 + 全部接口）
│  ├─ src/utils/            aiMode / format / gate / vision 小工具；src/styles/theme.css 主题与响应式
│  └─ package.json、vite.config.js、index.html
├─ business-service/        Spring Boot 3 + JPA + H2 文件库（8080）
│  ├─ src/main/java/com/dongchen/campus/
│  │  ├─ web/               11 个 Controller：Auth / Chat / Conversation / Diagnose / Plan / Practice / Knowledge / Profile / Student / Teacher / Meta
│  │  ├─ service/           14 个业务类：答疑编排 ChatService、诊断、计划、练习、统计、配置、会话、用户 Key、ReportMapper 等
│  │  ├─ domain/            10 个 @Entity（user_info、class_info、class_teacher_config、knowledge_point、student_kp_mastery、
│  │  │                     interaction_record、wrong_question、report、config_change_log、conversation）+ 7 个枚举
│  │  ├─ repository/        10 个 Spring Data Repository（与实体一一对应）
│  │  ├─ security/          AuthInterceptor、TokenService（HMAC-SHA256）、PasswordHasher（PBKDF2）、UserContext/CurrentUser
│  │  ├─ common/            CryptoUtil（AES-GCM 用户 Key 加密）、ApiResponse、ErrorCode、GlobalExceptionHandler
│  │  ├─ config/            AiProperties / AppProperties / AuthProperties / CryptoProperties、WebConfig、只读库自愈监听
│  │  ├─ ai/                AiServiceClient（RestClient 调 AI 8000，含超时与降级）
│  │  └─ seed/              DemoDataSeeder（2 班 / 2 师 / 5 生 / 67 知识点及掌握度）
│  ├─ src/main/resources/application.yml   端口、H2、密钥、默认班级
│  └─ src/test/java/        Java 单测 30/30（含 ApiIntegrationTest）
├─ ai-service/              FastAPI（8000）
│  ├─ app/main.py           路由挂载、启动建索引、健康检查
│  ├─ app/routers/          ai.py（答疑/诊断/计划/练习/检索）、knowledge.py（知识库与上传）
│  ├─ app/service.py        五类工作流编排（W0 意图识别 / W1 答疑 / W2 诊断 / W3 计划练习 / W4 配置抽取与班级分析）
│  ├─ app/retrieval.py      混合检索：0.55 余弦 + 0.45 词法，阈值 local 0.15 / openai 0.40
│  ├─ app/vector_store.py   LangChain InMemoryVectorStore 封装（KB 优先级加权）
│  ├─ app/embeddings.py     Embedding 双轨：local 字符 n-gram 哈希（1024 维）/ openai 兼容 bge-m3
│  ├─ app/knowledge.py      知识库导入与两级切分（5 文档 → 60 块 → 276 检索单元）
│  ├─ app/prompts.py、mock.py   提示词模板与 mock 兜底回答
│  ├─ app/rules.py、gate.py     硬拦截规则、前置自测状态机（SQLite 持久化）
│  ├─ app/vision.py         图片转文字（硅基流动 Qwen3-VL-8B）
│  ├─ app/llm.py、query.py   DeepSeek 调用、查询归一化与改写
│  ├─ knowledge/            kb1~kb5 五份知识库 md + knowledge_points.json（67 知识点）
│  ├─ tests/                pytest 61/61（test_api、test_gate_store）
│  └─ .env.example          配置模板（真实 .env 不入库）
├─ scripts/                 环境检查 / 启动 / 停止 / 重置 / 验收脚本（acceptance_check.py 24 项）
├─ docs/开发过程/           00 首次运行、01 接口契约（冻结，含 v1.2 §10）、02 Git、03 任务地图、04 实施方案、
│                          05 数据模型、06 部署运行、07 测试验收（含 v1.2 §9）、08 扣子映射、09 演示脚本、10 技术栈与架构、阶段进度记录
├─ docs/前情提要/           课程原始材料（扣子 PRD、工作流文档、对话历史；对话历史.txt 不入库）
├─ docs/知识库/             5 份知识库 md 的用户副本（运行时知识库在 ai-service/knowledge/）
├─ docs/运行截图/           运行截图 01~18（01 三端启动…18 教师重置密码）、截图要求与位置对照表.md、v1.1/（平台报送 18 张）
├─ coze/                   扣子原型材料（W0~W4 提示词、测试记录）
├─ 提交材料/                小组信息与分工、模板、提交文档（本地材料，整体已被 .gitignore 屏蔽，不入库）
└─ README.md
```

## 6. 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/开发过程/00-首次运行检查.md](docs/开发过程/00-首次运行检查.md) | 第一次跑通的最短路径 |
| [docs/开发过程/01-接口约定.md](docs/开发过程/01-接口约定.md) | **冻结契约**：端口、统一响应、鉴权、全部接口字段、枚举、账号、验收映射；**v1.2 增量见 §10、v1.3 增量见 §11**（多轮/用户 Key/检索增强；图片转文字/前置自测 gate） |
| [docs/开发过程/02-小组Git最小用法.md](docs/开发过程/02-小组Git最小用法.md) | 提交/拉取、忽略清单、冲突约定 |
| [docs/开发过程/03-开发任务地图.md](docs/开发过程/03-开发任务地图.md) | 阶段、负责人、状态、写范围、依赖顺序 |
| [docs/开发过程/04-实施方案.md](docs/开发过程/04-实施方案.md) | 架构、数据模型、RAG、mock/real、里程碑、风险 |
| [docs/开发过程/05-数据模型与初始化数据.md](docs/开发过程/05-数据模型与初始化数据.md) | 10 张表字段（PRD 7 核心 + 3 辅助：class_info / config_change_log / conversation）/ 索引 / 演示数据 / 掌握度规则 |
| [docs/开发过程/06-部署与运行手册.md](docs/开发过程/06-部署与运行手册.md) | 环境、启动、key、H2、常见问题（pip/npm 坑） |
| [docs/开发过程/07-测试与验收记录.md](docs/开发过程/07-测试与验收记录.md) | **实测记录**：v1.4.1 §12（gate 持久化：AI 61/61、真实重启 E2E、24/24）、v1.4 §11 的 24 项（**24/24 PASS**、C-22/C-23）、§10 v1.3 的 22 项（22/22 PASS、V-29~V-34）、v1.2 两轮 20/20、T-01~T-12 手工验收、缺陷与修复、验收结论 |
| [docs/开发过程/08-扣子到代码映射与提示词.md](docs/开发过程/08-扣子到代码映射与提示词.md) | W0~W4 → AI/Java 接口、提示词规则、约束落点 |
| [docs/开发过程/09-演示脚本与验收清单.md](docs/开发过程/09-演示脚本与验收清单.md) | 10~15 分钟演示时间轴、截图清单、8.1~8.3 对照 |
| [docs/开发过程/10-技术栈与架构说明.md](docs/开发过程/10-技术栈与架构说明.md) | 三层架构、技术栈清单、模块职责、关键数据流（含 v1.2 会话/用户 Key/Embedding 双轨、v1.3 图片链路与 gate 状态机、v1.4.1 gate SQLite 持久化 §4.12）、Mermaid 图 |
| [coze/01-提示词模板.md](coze/01-提示词模板.md) | W0~W4 全量提示词与接口对应 |
| [coze/02-测试记录模板.md](coze/02-测试记录模板.md) | 原型与集成阶段测试记录表 |

## 7. 验收对照（PRD 8.1~8.3）

| 验收项 | 实现要点 | 证据/用例 |
| --- | --- | --- |
| 8.1-1 答疑结合知识库讲解 | 向量检索 KB1~KB4，来源带 `citation`（文档+章节+得分） | C-07 / T-01 |
| 8.1-2 作业只给思路不给答案 | 提示词硬规则 + 后置答案校验 | C-08 / T-02 |
| 8.1-3 教师改难度后超难度拦截 | 每题/每次请求 clamp 到 `maxDifficulty` | C-15 / T-03 |
| 8.1-4 诊断出题+报告+掌握度同步 | 5 题诊断、错因四类、掌握度 ±、错题入本 | C-09~C-11 / T-04 |
| 8.1-5 计划/练习结构化输出 | 计划按天 JSON、A/B/C 分层、提示式 | C-12~C-13 / T-05 |
| 8.1-6 教师学情与学生记录一致 | 同源统计 `student_kp_mastery/wrong_question/interaction_record` | C-18 / T-06 |
| 8.2-1 知识库无内容明确告知 | 固定话术，不编造；检索未达阈值时**不返回来源** | T-07 / S-08 |
| 8.2-2 超范围必须拦截 | 固定拦截话术 `blocked=true`；前端先展示统一话术再显示判定依据。**v1.3 收窄**：硬拦截仅课程外数学与不当请求；教师配置的暂缓内容改前置自测后教学 | C-16 / C-16b / T-08 / S-07 |
| 8.2-3 配置修改立即生效 | Java 每次请求实时读配置 | C-15 / T-09 |
| 8.3-1 结构清晰公式可读 | KaTeX 渲染 + 分层输出 | T-10 / S-05 |
| 8.3-2 页面流畅无报错 | 骨架屏/空态/错误态/toast | T-11 |
| 8.3-3 配置操作简便有提示 | 配置表单 + 成功 toast + 变更日志 | T-12 / S-06 |

> **实测结论（v1.1，2026-11-07，real 模式）**：`scripts/acceptance_check.py` **20/20 PASS**（0 FAIL / 0 SKIP，退出码 0），AI 单测 35/35、Java 15/15；四类行为矩阵均按预期——命中给 `sources` + `citation`、超纲 `blocked=true` 统一话术、知识库未覆盖 `sources=[]` + 「知识库暂无相关内容」、非数学问题 `scopeWarning` 软提示。
>
> v1.2~v1.4.1 的实测结论、用例编号（C-/V-/T-）与缺陷记录见 [§10.1 版本演进](#101-版本演进) 与 [`docs/开发过程/07-测试与验收记录.md`](docs/开发过程/07-测试与验收记录.md) §9~§12。

## 8. 常用脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/检查环境.bat` | 检查工具版本、端口、venv、.env、node_modules |
| `scripts/启动AI服务.bat` / `启动Java服务.bat` / `启动Vue前端.bat` | 分别启动三端（自动建 venv、装依赖、设编码与缓存目录） |
| `scripts/启动全部服务.bat` / `停止全部服务.bat` | 一键启动（AI→Java→前端）/ 按端口停止（含 5174） |
| `scripts/重置H2数据.bat` | 停止服务后删除 H2 与 AI 索引状态，重启自动重建演示数据 |
| `scripts/acceptance_check.py` | 三端验收：v1.2 基线 20 项，v1.3 新增 C-16/C-16b/C-21 共 22 项，v1.4 新增 C-22（自助注册）/C-23（教师重置密码）共 **24 项**（`--base-java`/`--base-ai`/`--base-web`/`--skip-web`/`--timeout`），退出码 0/1/3 |

## 9. 常见问题

| 问题 | 处理 |
| --- | --- |
| pip 安装卡住 | `--no-cache-dir --disable-pip-version-check` + `TMP` 指到工作区（详见 docs/开发过程/06 §4.1） |
| npm `EPERM/EACCES` 或卡住 | 在 `frontend` 目录执行 `set npm_config_cache=..\.npm-cache` 后重装（或直接双击 `scripts/启动Vue前端.bat`，脚本已自动设好） |
| `mvnw.cmd` 首次下载卡住 | 用本机 Maven 3.9.x 完整路径，或教师提供离线 Maven（docs/开发过程/06 §3.2） |
| 端口占用 | `scripts/停止全部服务.bat`；仍占用用 `netstat -ano` 查 PID |
| 中文乱码 | 脚本已 `chcp 65001`；Java 已设 `-Dfile.encoding=UTF-8` |
| 401 / 一直跳登录 | 重新登录；确认 8080 已启动、token 未过期（7 天） |
| AI 回答像模板/没有 key 也能跑 | 检查 `ai-service/.env` 是否有 `DEEPSEEK_API_KEY` 并重启 AI；`/health` 的 `mode=mock` 说明无 key 走降级（属正常兜底） |
| `/health` 没有 vector 字段 / 知识库统计块数为 0 | 确认 AI 服务为 v1.1 且已启动完成；向量索引在启动与知识库变更后自动重建（`POST /ai/knowledge/rebuild`） |
| 改了配置但学生端没变化 | 学生端需**重新发起请求**；Java 每请求读库，不缓存；确认保存成功（`config_change_log`） |
| 公式显示源码 | `npm install` 后重启前端；确认 KaTeX 组件已挂载 |
| 换成 bge-m3 等语义 embedding 后，闲聊被判「知识库已覆盖」 | 语义向量分数基线高（无关 0.28~0.39），`local` 的 0.15 对 `openai` 过低；已按方案区分阈值：`openai` 用 `EMBEDDING_MIN_SCORE`（默认 0.40），`local` 用 `RETRIEVAL_MIN_SCORE`（0.15）；仍误判可调到 0.45~0.55 后重启 AI（docs/开发过程/06 §4.2） |
| 想用 DeepSeek 的 embeddings 接向量库 | DeepSeek 没有 embeddings 接口（`POST /embeddings` 实测 404）；v1.2 默认用本地哈希向量 + 混合检索，可选 `EMBEDDING_PROVIDER=openai` 接 OpenAI 兼容服务（缺 key 自动回退 local） |
| 来源条数与实际资料对不上 | v1.2 已按 `chunkId` 去重（同一段只留最高分）；来源卡片显示「知识库来源（N 段）」为去重后条数 |
| 回答里出现「片段 5」「kp031」 | v1.2 已做答案后处理，禁止内部编号；如仍出现，检查 AI 服务是否为最新版本并跑 `test_34` |
| 多轮追问不记得上文 / 会话丢失 | 确认答疑页使用的是同一会话（左侧列表）；后端 `GET /api/conversations/{id}` 应返回该会话全部消息 |
| 个人信息填了 Key 但没生效 | 开关「使用我的 Key」需打开并保存；顶栏徽标应变为 `real · 我的 Key`；Key 无效时自动降级系统 Key |
| 点「图片」提示「未配置识图模型…」 | 在 `ai-service/.env` 填 `VISION_API_KEY`（或复用 `EMBEDDING_API_KEY`）后重启 AI；`/health` 看 `vision_ready`，或改用文字输入（不影响主验收） |
| 图片识别失败 | 视觉模型超时/网络不可达/图片模糊；换清晰图重试，仍失败改文字输入（图片链路属 v1.3 增强项） |
| 教师禁用「级数」后学生不再被拦截，而是出现 3 道小题 | **v1.3 预期语义**：教师暂缓内容改为前置自测（≥2/3 通过后三步教学）；课程外数学（矩阵等）仍硬拦截。见 `docs/开发过程/01` §11.2 |
| 提交前置自测提示「前置测试已过期」 | **v1.4.1 起仅因 gate 创建超过 TTL（2 小时）**；已改 SQLite 持久化（`ai-service/data/gate.db`），服务重启不再丢 | 重新提问该知识点拿新 gate；彻底重置就停 AI 后删 `data/gate.db` 再启动（见 `docs/开发过程/06` §9） |
| 顶栏徽标显示 mock | `.env` 无 key 或调用失败降级；检查 `ai-service/.env` 的 `DEEPSEEK_API_KEY` 与 `/api/health` 的 `modelSource` |

## 10. 项目状态与团队

### 10.1 版本演进

| 版本 | 日期 | 这一版加了什么 | 实测结论 |
| --- | --- | --- | --- |
| v1.0 | 2026-10-25 | 三端跑通：7 表 + 鉴权 + 学生 8 页 / 教师 5 页 + 种子数据；无 key 走 mock，全流程可演示 | 20/20 PASS（mock），Java 13/13、AI 31/31 |
| v1.1 | 2026-11-07 | 用 LangChain 向量检索替换轻量 TF 检索；来源加 `citation` / `knowledgeCovered` / `scopeWarning`；默认 real 模式 | 20/20 PASS（real），AI 35/35、Java 15/15 |
| v1.2 | 2026-11-07 | ① 用户自带 AI Key（AES-GCM 加密、只回掩码）② 多轮会话与「继续对话」③ 检索增强 + 来源按 chunkId 去重 ④ 顶栏 AI 模式徽标 ⑤ 目录重组 | 20/20 PASS，AI 46/46、Java 19/19 |
| v1.3 | 2026-11-07 | ① 题目图片转文字（硅基流动 Qwen3-VL）② 教师暂缓内容改「3 题前置自测 → 通过后三步教学」③ 硬拦截收窄为课程外数学与不当请求 | 22/22 PASS |
| v1.4 | 2026-11-08 | ① 学生自助注册（注册即登录、默认班级、67 条掌握度）② 教师重置本班学生密码 | 24/24 PASS，Java 30/30 |
| v1.4.1 | 2026-11-08 | 前置自测 gate 状态改 SQLite 持久化，AI 重启后自测不丢 | 24/24 PASS，AI 61/61 |

> 每一版的用例编号（C-/V-/T-）、实测证据与缺陷记录见 `docs/开发过程/07-测试与验收记录.md`，判定标准见 `docs/开发过程/09-演示脚本与验收清单.md`，契约增量见 `docs/开发过程/01-接口约定.md` §10~§12。

### 10.2 当前实测指标

| 项 | 数值 |
| --- | --- |
| 自动化验收 | **24/24 PASS**（real，0 FAIL / 0 SKIP，退出码 0） |
| 单测 | AI **61/61**、Java **30/30**、前端构建 **48 modules** |
| 知识库 | 5 文档 / 60 块 / **276 检索单元** / 1024 维（bge-m3 语义向量，可回退 local 哈希） |
| 检索效果 | ∫2xe^x dx → 0.8862 第4章第4节 分部积分法（kp031）；洛必达 0.8484、泰勒余项 0.9060、定积分几何意义 0.9900 |
| 性能 | 学习计划生成 5~8s；索引重建 local 50~105ms / bge-m3 8.5s |
| 运行模式 | `AI_MODE=auto`：`.env` 有 key 即 real，无 key 自动降级 mock（离线仍可完整演示） |
| 三端 | AI 8000、Java 8080、前端 5173（必须 `http://localhost:5173`，Vite 只听 `::1`） |

### 10.3 提交截图清单（课程平台四类，共 17 项 / 18 张）

| 类别 | 编号 | 内容 | 状态 |
| --- | --- | --- | --- |
| Vue 前端（6） | V1~V6 | 登录页与双角色、学生首页、智能答疑与来源引用、诊断报告、学习计划、教师班级配置 | **6/6 已补** |
| Java 业务（3） | J1~J3 | 关键接口代码（ChatService）、数据库表清单（J2 为 v1.1 截图 9 张表，v1.2 后实库 10 张）、重要表数据 | **3/3 已补** |
| Python AI（4） | P1 | 与 AI 对话前端（与最终版 V3 同源） | 已补 |
| | P2 | Java 调用 Python 关键代码 | 已补 |
| | P3 | DeepSeek 开放平台用量/扣费截图（P3-1 用量信息页、P3-2 API keys 列表） | **已补（用户本人提供，2026-11-07）** |
| | P4 | 环境变量配置（key 打码） | 已补 |
| LangChain（4） | L1~L4 | 框架代码、文档导入向量库、检索定位章节、前端展示引用（L4 为最终裁剪版，1704×240，含得分 37%） | **4/4 已补** |

> 明细（要求解读/位置/合格判定/关联文档）见 [`docs/运行截图/截图要求与位置对照表.md`](docs/运行截图/截图要求与位置对照表.md)；旧版 S-01~S-16 截图保存在 `docs/运行截图/` 作为 v1.0 过程证据。
>
> **v1.4 过程截图（2026-11-08 09:57）**：`docs/运行截图/17-注册新用户.png`（S-17，登录页注册 tab 已填写）与 `18-教师重置学生密码.png`（S-18，教师端重置弹窗 + toast「密码已重置」）已归档，作为 A19/A20 的界面证据；平台四类必交截图不变，仍为 `v1.1/` 的 17 项 / 18 张。


- 团队：Lead（集成/契约）、ai-dev（AI 服务）、java-dev（Java 业务）、frontend-dev（前端）、docs-dev（文档/脚本/提交材料），分工与写范围见 `docs/开发过程/03` 与 `提交材料/小组信息与分工.md`（本地材料，不入库）。
- 约束：接口字段以 `docs/开发过程/01` 为准，任何人不得单方改契约；不提交密钥、H2 数据文件、`node_modules`、`.venv`。
