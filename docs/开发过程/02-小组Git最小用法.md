# 小组 Git 最小用法（本项目版）

> 课程只要求掌握「代码不丢、改动不互相覆盖」的最小 Git 操作。本项目为课程实训全量实现，建议从 M0（脚手架跑通）起就建立仓库，之后每个里程碑提交一次。
> 本文件面向小组同学；本文档不等于要求使用复杂分支模型。

## 1. 小组规则

- 每人使用**同一个仓库**，不能各自保存一份互不相关的最终项目；
- 由组长（或指定 1 人）负责建仓库、合并与最终备份，其他人也必须提交自己负责的内容；
- 每次开始前先 `git pull`，结束前 `git add/commit/push`；
- **两人不同时改同一个文件**：本项目已按目录划分写范围（见 `docs/开发过程/03-开发任务地图.md`），前端页面、Java 控制器/服务、AI 模块、文档分别归不同人；
- 冲突时停止推送，保留报错与冲突文件，禁止强制覆盖。
- **v1.2 目录调整（2026-11-07）**：`开发文档/` → `docs/前情提要/`、`文献材料/` → `docs/知识库/`、`docs/00~10` → `docs/开发过程/`，全部用 `git mv` 保留提交历史；`.gitignore` 同步改为忽略 `docs/前情提要/` 与 `对话历史.txt`；拉取后如本地仍有旧目录，先 `git pull` 再手动删除空目录，不要用 `git add -A` 盲提。

## 2. 第一次获取项目

```bash
git clone <仓库地址>
cd AmsLearn
```

课堂暂时没有远程仓库时，由组长保留统一主项目，并在每次课后打包备份（含 `docs/`、`coze/`、`提交材料/`）。

## 3. 每次开始开发

```bash
git pull
git status
```

确认拿到最新代码再动手；如果 `git status` 显示别人有未提交改动，先沟通，不要直接覆盖。

## 4. 每次完成开发

```bash
git status
git add frontend/src/views/StudentTutor.vue   # 只加自己负责的文件
git commit -m "feat(前端): 学生答疑页对接 /api/chat 并渲染资料来源"
git pull
git push
```

提交信息格式（推荐，便于教师核对分工）：

```text
feat(范围): 做了什么          # 新功能
fix(范围): 修了什么           # 缺陷
docs(范围): 哪份文档           # 文档
chore(范围): 脚本/构建          # 杂项
```

范围取 `前端/Java/AI/文档/脚本` 之一；例如 `feat(Java): 实现教师配置读改与变更日志`。

## 5. 哪些文件不要提交

```gitignore
frontend/node_modules/
frontend/dist/
.npm-cache/
.tmp/
ai-service/.venv/
ai-service/.env
ai-service/data/
business-service/target/
business-service/data/
**/__pycache__/
*.log
```

- `ai-service/.env` 含 DeepSeek key，**绝不能提交**；提交 `.env.example` 即可；
- H2 数据文件（`business-service/data/*.db`）是本地演示数据，不提交，重置方法见 `docs/开发过程/06`；
- `node_modules`、`.venv` 可由 `npm install` / `pip install -r requirements.txt` 重装，不提交。

## 6. 本项目容易冲突的共享点（提前约定）

| 文件 | 约定 |
| --- | --- |
| `frontend/src/App.vue` | 由 frontend-dev 负责路由/挂载，其他人不改 |
| `frontend/src/api.js` | 由 frontend-dev 统一维护，新增接口先沟通 |
| `business-service/src/main/resources/application.yml` | 由 java-dev 维护，端口/数据源不得私改 |
| `ai-service/app/main.py` | 由 ai-dev 装配路由，其他人不加路由 |
| `docs/开发过程/01-接口约定.md` | **冻结契约，只读**；调整必须先经 Lead 确认并全员同步 |
| `README.md` / `docs/` | 由 docs-dev 统一更新 |

## 7. 本课程不要求掌握

- 复杂分支模型（Git Flow）、rebase、cherry-pick；
- 强制推送与历史重写。

禁止在不理解影响时使用 `git push --force`、`git reset --hard`。发生冲突先找组长或教师。

## 8. 教师抽查依据

每名成员应有与分工相符的提交记录，并能讲清自己负责的页面/接口/模块。只有组长一人有提交记录，不能证明其他成员完成开发；建议每周至少每人 1 次有意义的提交（代码或文档）。
