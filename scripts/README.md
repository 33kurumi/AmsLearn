# scripts 脚本说明

Windows 批处理与验收脚本集合。所有 bat 均自带 `chcp 65001`（UTF-8 中文不乱码），并 `cd /d %~dp0..` 切到项目根，可双击运行也可在任意目录调用。

## 1. 脚本清单

| 文件 | 作用 | 关键行为 |
| --- | --- | --- |
| `检查环境.bat` | 环境体检 | 检查 Node/npm、JDK≥17、Maven Wrapper、Python、端口 8000/8080/5173/5174、`ai-service/.venv`、`.env`、`frontend/node_modules` |
| `启动AI服务.bat` | 启动 FastAPI（8000） | 无 venv 则自动创建并 `pip install -r requirements.txt`；无 `.env` 提示将用 mock；检查端口占用；`uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| `启动Java服务.bat` | 启动 Spring Boot（8080） | 检测 java 版本（<17 报错）、由 java 路径推导 `JAVA_HOME`、设 `MAVEN_OPTS=-Dfile.encoding=UTF-8`、检查 8080、`call mvnw.cmd spring-boot:run` |
| `启动Vue前端.bat` | 启动 Vite（5173） | 设 `npm_config_cache` 到工作区 `.npm-cache`，缺 `node_modules` 时 `npm install`，检查 5173，`npm run dev` |
| `启动全部服务.bat` | 一键启动 | 新窗口依次启动 AI → Java → 前端，各间隔 5 秒 |
| `停止全部服务.bat` | 一键停止 | 按端口 8000/8080/5173/5174 找 PID 并 `taskkill` |
| `重置H2数据.bat` | 重置演示数据 | 需先停服务；`choice` 二次确认后删除 `business-service/data/student-project*.db` 与 `ai-service/data/knowledge_state.json`，重启自动重建种子数据 |
| `acceptance_check.py` | 三端验收 | Python 标准库 urllib；v1.2 基线 20 用例 C-01~C-20，v1.3 新增 C-16（gate 状态机）/C-16b（矩阵硬拦截）/C-21（图片转文字，未配视觉 key 记 SKIP），v1.4 新增 C-22（自助注册）/C-23（教师重置密码），共 **24 项**；输出 PASS/FAIL/SKIP 表与退出码；三端未全启不崩溃（全部 SKIP） |


> **v1.2 说明（2026-11-07）**：v1.2 未新增脚本，启动/停止/重置方式不变。差异只有两点——(1) `恢复/重置` 也会清空 v1.2 新增的 `conversation` 会话数据（重置即删除整个 H2 文件，重启后重建演示数据）；(2) 可选配置 `ai-service/.env` 的 `EMBEDDING_PROVIDER`（默认 `local`，无需额外 Key）、`QUERY_EXPANSION`，学生自填 Key 走页面「个人信息 → AI 模型设置」，不需要改脚本或环境变量。

> **v1.3 说明（2026-11-07 17:35，已实测）**：脚本本身无需改动。`acceptance_check.py` 新增 3 条用例（C-16/C-16b/C-21，共 22 项），其中 C-21 依赖外部视觉服务（硅基流动 Qwen3-VL），**未配置视觉 key 时记 SKIP 不记 FAIL**；2026-11-07 17:35 三端 real 实测 **22/22 PASS**（0 FAIL、0 SKIP、退出码 0，`.tmp/acceptance-v13-final.txt`），明细见 `docs/开发过程/07` §10。

> **v1.4 说明（2026-11-08 09:57，已实测）**：脚本本身无需改动启动逻辑。`acceptance_check.py` 新增 2 条用例（C-22 自助注册、C-23 教师重置密码，共 **24 项**），两者均不依赖外部 Key；2026-11-08 09:57 三端 real 实测 **24/24 PASS**（0 FAIL、0 SKIP、退出码 0，`.tmp/acceptance-v14-final.txt`），明细见 `docs/开发过程/07` §11。`重置H2数据.bat` 行为不变（重建后注册用户与重置密码结果一并清空）。

## 2. 推荐使用顺序

1. 首次：`检查环境.bat` → 按提示补齐环境与依赖；
2. 每次开发：`启动全部服务.bat`（或分别启动）；
3. 联调后：`acceptance_check.py`；
4. 演示前如需干净数据：`停止全部服务.bat` → `重置H2数据.bat` → 再启动；
5. 结束：`停止全部服务.bat`。

## 3. 验收脚本用法

```bat
:: 在项目根目录（含 README.md 的 AmsLearn 文件夹）内执行
ai-service\.venv\Scripts\python.exe scripts\acceptance_check.py
```

参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--base-java` | `http://localhost:8080` | Java 业务服务地址 |
| `--base-ai` | `http://localhost:8000` | AI 服务地址 |
| `--base-web` | `http://localhost:5173` | 前端地址 |
| `--skip-web` | 关闭 | 跳过前端页面检查（仅测接口时用） |
| `--timeout` | 5 秒 | 普通请求超时 |
| `--ai-timeout` | 90 秒 | AI 请求超时（真实模型可能较慢） |
| `--verbose` | 关闭 | 打印失败详情/响应片段 |

退出码：`0` 全部 PASS；`1` 存在 FAIL；`3` 存在 SKIP（服务未启动或前置未就绪，属「Not Ready」而非失败）。三端未全部启动时逐项输出 `[SKIP]` 并给出启动提示，不会抛异常退出。

## 4. 常见问题

| 现象 | 处理 |
| --- | --- |
| bat 窗口一闪而过 | 从 cmd 运行看报错；或检查是否被杀毒拦截 |
| AI 启动时报依赖缺失 | 删 `ai-service/.venv` 重跑 `启动AI服务.bat`；受限环境按 docs/开发过程/06 §4.1 的 `--no-cache-dir` 命令安装 |
| Java 启动报 `JAVA_HOME` 不对 | 脚本会按 `java -version` 推导；仍失败则手动设 `JAVA_HOME` 到 JDK 17 |
| 端口占用 | `停止全部服务.bat`；再不行用 `netstat -ano` 查 PID 后结束 |
| 重置 H2 失败 | 先停 Java 服务（文件被锁）；确认 `business-service/data` 存在 |
| 验收脚本全 SKIP | 三端未启动：先 `启动全部服务.bat`；或地址参数写错（端口 8080/8000/5173） |
| 中文乱码 | 脚本已 UTF-8；在旧控制台手动运行时先 `chcp 65001` |
