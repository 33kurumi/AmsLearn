# 知学 AI · 个性化学习导师（前端）

Vue 3 + Vite 6 单页应用，面向高等数学考研个性化学习场景。前端不引入 vue-router，
由 `src/App.vue` 承担「外壳」职责（登录态、角色导航、页面切换），页面按角色拆分到
`src/views/student` 与 `src/views/teacher`。

## 快速开始

```bash
# 安装依赖（首次）
npm install

# 开发（默认 5173，需 Java 业务服务运行在 8080）
npm run dev
npm run dev -- --port 5174

# 生产构建（产物在 dist/）
npm run build

# 预览构建产物
npm run preview
```

演示账号（密码均为 `123456`）：

| 账号 | 角色 | 说明 |
| --- | --- | --- |
| student1 | 学生 | 张同学，C-GS-01 |
| student2 ~ student5 | 学生 | 用于排行榜/班级学情演示 |
| teacher1 / teacher2 | 教师 | 班级配置、学情分析、知识库管理 |

## 接口约定

- 统一前缀：`VITE_API_BASE`，缺省为 `http://localhost:8080/api`（见 `src/api.js`）。
- 鉴权：登录后 token 存 `localStorage.ams_token`，用户信息存 `localStorage.ams_user`；所有请求自动带 `Authorization: Bearer <token>`。
- 统一响应：`{ success, message, data, code }`；`success=false` 抛错，`401` 清除 token 并回到登录页。
- 字段定义以 `docs/开发过程/01-接口约定.md` 为唯一依据（契约文档已随全局目录调整迁移到 `docs/开发过程/`）。
- 若把 `VITE_API_BASE` 配成相对路径 `/api`，开发服务器会按 `vite.config.js` 中的 proxy 转发到 8080，避免跨域。

## 目录结构

```
src/
  api.js                 # fetch 封装：超时（普通 20s / AI 90s）、Bearer、401、错误归一化
  App.vue                # 外壳：登录态、角色导航、页面切换、健康检查
  main.js
  toast.js               # 全局 toast
  styles/theme.css       # 全站主题（保留原「知学 AI」深绿视觉）
  utils/format.js        # 枚举文案、时间/百分比格式化
  utils/vision.js        # v1.3 图片校验 / 尺寸计算 / canvas 压缩
  utils/gate.js          # v1.3 前置自测字段归一化与校验
  components/            # ToastHost / MarkdownView / MasteryBars / Skeleton / Empty / Error / GateCard
  views/
    LoginView.vue
    student/             # 首页概览、答疑辅导、知识诊断、学习计划、分层练习、学习记录、错题复盘、个人信息
    teacher/             # 学情总览、班级配置、班级学情、知识库管理、学生记录、个人信息
scripts/
  build.mjs / dev.mjs    # 构建与开发入口（见下方「受限环境说明」）
  sandbox-cp-patch.cjs   # 子进程补丁
```

## v1.2 会话式答疑与 AI 设置

- 顶栏 / 登录页展示 AI 模式徽标：`real · 模型 · 系统 Key`、`real · 模型 · 我的 Key` 或 `mock`。登录后徽标以 `GET /api/health` 为基础，并额外拉取 `GET /api/profile/ai`：当个人配置 `enabled=true` 且 `hasApiKey=true` 时显示「我的 Key」（模型优先取个人配置的 model），未配置或接口 404 时保持系统 Key 展示；个人信息页保存 / 清除 Key 后徽标立即刷新。
- 答疑辅导改为会话式：左侧会话列表（新建 / 切换 / 重命名 / 删除），发送消息携带 `conversationId`；切回历史会话会加载完整消息。
- 回答末尾展示本次使用的模式与 Key 来源标签；知识库来源按 `chunkId` 去重后显示「知识库来源（N 段）· 已按片段去重」。
- 学习记录的答疑记录行提供「继续对话」，跳转答疑页并载入对应会话。
- 个人信息页（学生 / 教师）新增「AI 模型设置」：可填写自己的 Base URL、模型与 API Key（掩码显示、支持替换 / 清除），默认使用系统 Key。
- 相关接口未就绪（404）时页面降级提示，不白屏；AI 请求超时 90 秒并给出重试。

## v1.3 图片答疑与前置自测

- 答疑输入区新增图片按钮：支持 PNG / JPEG / WebP / GIF，单张 ≤ 5MB；前端用原生 canvas 压缩（最长边 ≤ 1600px、JPEG q=0.85，不新增依赖），识别期间显示缩略图与进度，识别出的文字回填输入框、可编辑后发送；图片不落库，历史会话只保存文字。
- 图片识别接口为 `POST /api/student/chat/vision`（multipart 字段 `file`，超时 60s）。后端未就绪（404）时提示「后端暂未提供图片识别接口（404），请先手动输入问题。」，仍可手动输入，不白屏。
- AI 需要先补前置知识时，回答气泡内渲染「前置自测」卡片（3 道单选、知识点与难度、通过线 2/3）。提交 `POST /api/student/gate/check`，请求体 `{ gateId, conversationId, answers: [{ questionId, choice }] }`。
- 通过后展示三步讲解（teaching.steps）、答案、引用来源与模式标签；未通过展示得分、反馈与薄弱前置，可重新测试；过期提示重新提问。历史会话中的自测卡只保留只读摘要，不展示题目。
- 相关工具函数：`src/utils/vision.js`（校验 / 压缩）、`src/utils/gate.js`（字段兼容 camelCase 与 snake_case）、`src/components/GateCard.vue`。

## Markdown 与数学公式

- AI 回答统一按 Markdown 渲染（`marked`）。
- 数学公式支持 `$...$` 与 `$$...$$`（KaTeX），由 `src/components/MarkdownView.vue` 完成渲染与 HTML 白名单清洗（移除 script/iframe/on* 属性等）。

## 受限环境说明（为什么 scripts/ 下有自定义入口）

Vite 默认在构建期通过 esbuild 启动子进程服务、并在 Windows 上执行 `exec("net use")` 探测网络盘。
在禁止「带管道 stdio 的子进程」的受限环境（如本机 DSH 沙箱、部分企业安全策略）中，这两处会直接
`spawn EPERM`。因此：

- `vite.config.js` 使用纯 JS 插件完成 `process.env` / `import.meta.env` / `__VUE_*` 的 define 替换，
  并在构建期移除内置 `vite:define` 插件；关闭 `esbuild`、`build.minify`、`build.cssMinify`、目标 `esnext`、开发态依赖预构建。
- `scripts/build.mjs`、`scripts/dev.mjs` 在加载 Vite 前先打补丁，避免 `net use` 探测崩栈。

在正常环境（可自由启动子进程）中，这些脚本产出的结果与官方 `vite build` / `vite dev` 一致；
如需恢复默认行为，可把 `package.json` 的脚本改回 `vite` / `vite build` 并删除 `vite.config.js` 中的
`app:define-replacement` 插件与 `esbuild:false`、`optimizeDeps` 配置。

## 后端未就绪时的表现

业务服务（8080）未启动时不会白屏：登录页显示「业务服务未连接」提示；登录后各页面统一走
「加载骨架屏 → 错误态（含重试按钮）」，接口错误信息会给出服务未启动的排查提示。
