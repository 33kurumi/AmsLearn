# 知识资料目录

本目录存放 AI 服务检索用的课程资料，均为可公开的课程内容，来源为 `docs/知识库/` 下对应 5 份「知识库版」文档（原文件保留在 `docs/知识库/`，此处为副本）。

## 目录说明

| 目录 | KB | scope | 内容 | 对外 |
| --- | --- | --- | --- | --- |
| `kb1_outline/` | KB1 | GLOBAL | 课程大纲：章节、课时、教学目标、重难点 | 是（检索来源） |
| `kb2_textbook/` | KB2 | GLOBAL | 教材讲义：概念、定理、例题与解题思路 | 是（检索来源） |
| `kb3_questions/` | KB3 | GLOBAL | 题库与解析：题目、难度、题型、解题思路 | 是（出题来源） |
| `kb4_teacher/` | KB4 | GLOBAL | 教师授权资料：教学建议、易错点、讲法 | 是（可在教师配置中关闭） |
| `kb5_graph/` | KB5 | GLOBAL | 知识图谱：知识点前后置关系 | 否（仅后台计算） |
| `uploads/<classId>/` | 由上传时指定 | CLASS | 教师上传的班级资料 | 是（仅本班） |

- `knowledge_points.json`：67 个知识点（kp001~kp067），含 kpId/kpName/chapter/difficulty/objectives 等字段，供出题、诊断报告、学习计划使用。
- 内置资料清单与文件名在 `app/config.py` 的 `SEED_DOCUMENTS` 中维护；新增内置资料需同时放入对应目录并登记。

## 资料要求

- 使用 `.md` 或教师指定的文本格式，UTF-8 编码；
- 删除身份证号、手机号、住址等个人信息；
- 记录资料名称、来源和更新时间；
- 不确定或过期的内容不作为确定结论；
- 至少准备一条资料未覆盖的问题，用于验证「无答案处理」（本服务已内置：`/qa` 返回「知识库暂无相关内容…」）。

## 索引与状态

- 服务启动时自动扫描本目录并重建索引；也可调用 `POST /knowledge/rebuild` 手动重建。
- 分块参数：600~800 字/块、重叠约 100 字；检索 Top8；阈值随 embedding 方案（local 哈希 0.15 / openai 语义 0.40），见 `.env` 的 `RETRIEVAL_MIN_SCORE` 与 `EMBEDDING_MIN_SCORE`。
- 文档启停状态持久化在 `ai-service/data/knowledge_state.json`；内置资料可停用、不可删除。
- 教师上传的班级资料保存在 `uploads/<classId>/`，可通过 `/knowledge/upload`、`PATCH /knowledge/documents/{id}`、`DELETE /knowledge/documents/{id}` 管理。
