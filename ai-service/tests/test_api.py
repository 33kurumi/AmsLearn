# -*- coding: utf-8 -*-
r"""AI 服务接口自测：覆盖 AI1~AI16 与 4 个验收场景。

运行方式（工作目录 ai-service）：
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

说明：使用 FastAPI TestClient 并以 with 方式触发 lifespan（启动时重建知识库索引），
全部用例基于 mock 模式运行，不依赖 DeepSeek API Key。
"""

import json
import logging
import os
import sys
import unittest
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 必须在导入 app 之前设置：配置层使用 dotenv override=False，环境变量优先级最高。
# 测试必须离线、确定性运行，不允许因为本机 .env 里的真实 key 走到 real 模式；
# 同理强制本地哈希 embedding，避免本机 .env 配了硅基流动/OpenAI 时测试依赖外网。
os.environ["AI_MODE"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "local"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.prompts import BLOCK_MESSAGE  # noqa: E402
from app.rules import SOFT_SCOPE_WARNING  # noqa: E402

SECTIONS = ["【先判断】", "【思路引导】", "【知识点讲解】", "【易错提醒】", "【下一步】"]
ERROR_TYPES = {"概念混淆", "计算失误", "审题偏差", "方法不当"}
LEVELS = {"优秀", "良好", "一般", "待提升"}

QA_BASE = {"userId": 1, "role": "STUDENT", "classId": "C-GS-01"}
DIAG_BASE = {"classId": "C-GS-01"}


class ApiTest(unittest.TestCase):
    """AI 服务全量接口测试。"""

    client = None

    @classmethod
    def setUpClass(cls):
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()
        # 若历史状态中内置文档被停用，恢复启用，保证断言稳定
        cls.client.patch("/knowledge/documents/kb1-outline", json={"enabled": True})
        cls.client.patch("/knowledge/documents/kb2-textbook", json={"enabled": True})
        cls.client.patch("/knowledge/documents/kb3-questions", json={"enabled": True})
        cls.client.patch("/knowledge/documents/kb4-teacher", json={"enabled": True})
        cls.client.patch("/knowledge/documents/kb5-graph", json={"enabled": True})

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    # ---------------------------------------------------------------- helpers
    def post(self, path, payload, expected=200):
        resp = self.client.post(path, json=payload)
        self.assertEqual(resp.status_code, expected, msg="%s -> %s" % (path, resp.text[:500]))
        return resp.json()

    def get(self, path, expected=200):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, expected, msg="%s -> %s" % (path, resp.text[:500]))
        return resp.json()

    def ask(self, message, **extra):
        payload = dict(QA_BASE)
        payload.update(extra)
        payload["message"] = message
        return self.post("/qa", payload)

    def diagnostic_questions(self, **payload):
        body = dict(DIAG_BASE)
        body.update(payload)
        return self.post("/diagnose/questions", body)["questions"]

    # ------------------------------------------------------------ AI1 /health
    def test_01_health(self):
        data = self.get("/health")
        self.assertEqual(data["status"], "UP")
        self.assertIn(data["mode"], {"mock", "real"})
        self.assertTrue(data["model"])
        self.assertIsInstance(data["llm_ready"], bool)
        self.assertGreaterEqual(data["knowledge_documents"], 5)
        self.assertGreater(data["knowledge_chunks"], 10)
        # 契约 v1.1：健康检查暴露向量索引信息
        self.assertTrue(data["vector_store"])
        self.assertTrue(data["embedding"])
        self.assertEqual(data["vector_dim"], 1024)
        self.assertGreater(data["vector_count"], 0)

    # --------------------------------------------------------------- AI2 /qa
    def test_02_qa_concept(self):
        data = self.ask("洛必达法则的使用条件是什么")
        self.assertFalse(data["blocked"])
        self.assertEqual(data["intent"], "qa")
        self.assertIn(data["mode"], {"mock", "real"})
        self.assertAlmostEqual(sum(data["answer"].count(s) for s in SECTIONS), len(SECTIONS))
        self.assertIsInstance(data["sources"], list)
        self.assertGreater(len(data["answer"]), 120)
        self.assertIn("kp021", data["kpIds"])
        # 契约 v1.1：命中知识库时必须标记覆盖，并给出可回溯的 citation
        self.assertTrue(data["knowledgeCovered"])
        self.assertIsNone(data["scopeWarning"])
        self.assertTrue(data["sources"])
        citation = data["sources"][0]["citation"]
        self.assertTrue(citation.startswith("《"), msg=citation)
        self.assertIn("第3章", citation)
        self.assertIn("第3节", citation)
        self.assertIn("【参考资料】", data["answer"])

    def test_03_qa_scope_blocked(self):
        """验收场景 2：超范围问题必须 blocked=true 且统一话术。"""
        data = self.ask("线性代数矩阵特征值怎么求")
        self.assertTrue(data["blocked"])
        self.assertEqual(data["answer"], BLOCK_MESSAGE)
        self.assertTrue(data["blockReason"])
        self.assertEqual(data["sources"], [])
        self.assertFalse(data["knowledgeCovered"])
        self.assertIsNone(data["scopeWarning"])

    def test_04_qa_homework_refusal(self):
        """验收场景 3：作业/考试题拒绝直接给最终答案，但给出五段引导。"""
        data = self.ask("求极限 lim(x->0) sin3x/x 的值，这是作业第3题，直接给答案")
        self.assertFalse(data["blocked"])
        for section in SECTIONS:
            self.assertIn(section, data["answer"])
        self.assertIn("不能直接给出最终答案", data["answer"])
        self.assertNotIn("答案是", data["answer"])
        self.assertNotIn("最终结果", data["answer"])

    def test_05_qa_soft_scope(self):
        """非数学话题：不硬拦截，但 knowledgeCovered=false 并给出统一软提示。"""
        data = self.ask("今天天气怎么样")
        self.assertFalse(data["blocked"])
        self.assertFalse(data["knowledgeCovered"])
        self.assertEqual(data["scopeWarning"], SOFT_SCOPE_WARNING)
        self.assertEqual(data["sources"], [])
        self.assertGreater(len(data["answer"]), 40)

    def test_06_qa_action_hint(self):
        data = self.ask("我想做几道练习巩固一下")
        self.assertIn(data["intent"], {"practice", "plan", "qa", "diagnose"})
        action = data["action"]
        if action is not None:
            self.assertTrue(action.get("type"))
            self.assertTrue(action.get("payload") is not None or action.get("label"))

    # ------------------------------------------------------------ AI3 /intent
    def test_07_intent(self):
        data = self.post("/intent", {"message": "帮我生成一周学习计划", "role": "STUDENT"})
        self.assertEqual(data["intent"], "plan")
        self.assertGreater(data["confidence"], 0)
        self.assertIsInstance(data["kpIds"], list)
        self.assertTrue(data["reason"])

        data = self.post("/intent", {"message": "洛必达法则的条件是什么", "role": "STUDENT"})
        self.assertEqual(data["intent"], "qa")

    # ---------------------------------------------------------- AI4 /retrieve
    def test_08_retrieve(self):
        data = self.post("/retrieve", {"query": "洛必达法则适用条件", "topK": 8, "minScore": 0.15})
        self.assertTrue(data["enough"])
        self.assertGreater(data["topScore"], 0)
        self.assertTrue(1 <= len(data["items"]) <= 8)
        item = data["items"][0]
        for key in ("documentId", "kb", "title", "excerpt", "score", "citation", "chapter", "section"):
            self.assertIn(key, item)
        self.assertIn(data["mode"], {"mock", "real"})
        self.assertTrue(item["citation"].startswith("《"))
        self.assertTrue(item["section"])
        self.assertIn("第", item["citation"])

    def test_09_retrieve_not_enough(self):
        """验收场景 1：知识库无相关内容时 enough=false。"""
        data = self.post("/retrieve", {"query": "今天天气怎么样", "topK": 8, "minScore": 0.15})
        self.assertFalse(data["enough"])
        self.assertEqual(data["items"], [])

    # ------------------------------------------------- AI5 /diagnose/questions
    def test_10_diagnose_questions_quick(self):
        questions = self.diagnostic_questions(mode="QUICK")
        self.assertEqual(len(questions), 5)
        for q in questions:
            self.assertTrue(q["questionId"])
            self.assertTrue(q["kpId"])
            self.assertTrue(q["stem"])
            self.assertTrue(q["answerKey"])
            self.assertTrue(q["analysis"])
            self.assertIn(q["type"], {"SINGLE", "JUDGE", "FILL"})

    def test_11_diagnose_questions_difficulty_filter(self):
        """验收场景 4：题目难度不得超过 difficultyMax。"""
        questions = self.diagnostic_questions(mode="QUICK", count=5, difficultyMax=2)
        self.assertEqual(len(questions), 5)
        for q in questions:
            self.assertLessEqual(q["difficulty"], 2)
        self.assertGreaterEqual(len({q["kpId"] for q in questions}), 2)

    def test_12_diagnose_questions_full(self):
        questions = self.diagnostic_questions(mode="FULL", difficultyMax=4)
        self.assertEqual(len(questions), 15)
        self.assertGreaterEqual(len({q["kpId"] for q in questions}), 5)

    # ------------------------------------------------------ AI6 /diagnose/grade
    def test_13_grade_all_correct(self):
        questions = self.diagnostic_questions(mode="QUICK", count=5, difficultyMax=3)
        answers = [{"questionId": q["questionId"], "answer": q["answerKey"]} for q in questions]
        data = self.post("/diagnose/grade", {"questions": questions, "answers": answers})
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["correctCount"], 5)
        self.assertEqual(data["score"], 100)
        self.assertEqual(data["level"], "优秀")
        self.assertEqual(data["errorSummary"], [])
        self.assertTrue(data["advice"])

    def test_14_grade_with_errors(self):
        questions = self.diagnostic_questions(mode="QUICK", count=5, difficultyMax=3)
        first = questions[0]
        answers = [{"questionId": first["questionId"], "answer": first["answerKey"]}]
        answers += [{"questionId": q["questionId"], "answer": "这是错误答案"} for q in questions[1:]]
        data = self.post("/diagnose/grade", {"questions": questions, "answers": answers})
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["correctCount"], 1)
        self.assertEqual(data["score"], 20)
        self.assertEqual(data["level"], "待提升")
        self.assertTrue(data["results"][0]["correct"])
        wrong = [r for r in data["results"] if not r["correct"]]
        self.assertEqual(len(wrong), 4)
        for item in wrong:
            self.assertIn(item["errorType"], ERROR_TYPES)
        self.assertTrue(data["errorSummary"])
        self.assertEqual(sum(e["count"] for e in data["errorSummary"]), 4)
        self.assertTrue(data["advice"])

    def test_15_grade_fill_normalization(self):
        questions = [{
            "questionId": "fill-1", "index": 1, "kpId": "kp021", "kpName": "洛必达法则",
            "difficulty": 2, "type": "FILL", "stem": "求极限 lim(x→0) sin3x/x。",
            "options": [], "hint": "", "answerKey": "3", "analysis": "", "layer": "B",
        }]
        answers = [{"questionId": "fill-1", "answer": " ３ "}]
        data = self.post("/diagnose/grade", {"questions": questions, "answers": answers})
        self.assertEqual(data["score"], 100)
        self.assertEqual(data["level"], "优秀")

    # -------------------------------------------------- AI7 /practice/questions
    def test_16_practice_layer_b(self):
        data = self.post("/practice/questions", {"layer": "B", "count": 3, "difficultyMax": 3})
        self.assertEqual(len(data["questions"]), 3)
        self.assertTrue(data["guidance"])
        for q in data["questions"]:
            self.assertIsNone(q["answerKey"])
            self.assertTrue(q["hint"])
            self.assertIn(q["difficulty"], {2, 3})
            self.assertEqual(q["layer"], "B")

    def test_17_practice_layer_a(self):
        data = self.post("/practice/questions", {"layer": "A", "count": 3, "difficultyMax": 2})
        self.assertEqual(len(data["questions"]), 3)
        for q in data["questions"]:
            self.assertIn(q["difficulty"], {1, 2})
            self.assertLessEqual(q["difficulty"], 2)

    # ------------------------------------------------------ AI8 /practice/hint
    def test_18_practice_hint(self):
        question = self.post("/practice/questions", {"layer": "B", "count": 2, "difficultyMax": 3})["questions"][0]
        data = self.post("/practice/hint", {"question": question, "studentAnswer": ""})
        self.assertTrue(data["hint"])
        self.assertIn("第 1 步", data["hint"])
        self.assertIn("第 2 步", data["hint"])
        self.assertNotIn("最终答案", data["hint"])
        self.assertTrue(data["strategy"])

    def test_19_practice_hint_no_leak(self):
        question = {
            "questionId": "q-x", "index": 1, "kpId": "kp021", "kpName": "洛必达法则",
            "difficulty": 2, "type": "FILL", "stem": "求 lim(x->2) (x^2-4)/(x-2)。",
            "options": [], "hint": "先因式分解", "answerKey": "4", "analysis": "", "layer": "B",
        }
        data = self.post("/practice/hint", {"question": question, "studentAnswer": "0"})
        self.assertNotIn("=4", data["hint"].replace(" ", ""))
        self.assertNotIn("答案是", data["hint"])

    # ---------------------------------------------------------------- AI9 /plan
    def test_20_plan_week(self):
        payload = {
            "period": "WEEK", "days": 7, "goal": "两周内突破极限与导数",
            "focusKpIds": ["kp004", "kp021"], "classId": "C-GS-01",
            "mastery": [
                {"kpId": "kp021", "kpName": "洛必达法则", "mastery": 35},
                {"kpId": "kp004", "kpName": "函数的极限与极限运算法则", "mastery": 55},
            ],
        }
        data = self.post("/plan", payload)
        self.assertEqual(len(data["days"]), 7)
        self.assertTrue(data["summary"])
        self.assertIn(data["mode"], {"mock", "real"})
        for index, day in enumerate(data["days"], start=1):
            self.assertEqual(day["dayIndex"], index)
            self.assertTrue(day["goal"])
            self.assertTrue(day["study"]["summary"])
            self.assertTrue(day["study"]["points"])
            self.assertTrue(day["study"]["example"])
            self.assertGreaterEqual(len(day["practiceQuestions"]), 2)
            self.assertTrue(day["review"]["summary"])
            self.assertTrue(day["review"]["checklist"])

    def test_21_plan_day(self):
        data = self.post("/plan", {"period": "DAY", "days": 1, "goal": "复习洛必达法则"})
        self.assertEqual(len(data["days"]), 1)

    # ------------------------------------------------------ AI10 /class-analysis
    def test_22_class_analysis(self):
        payload = {
            "period": "7D", "classId": "C-GS-01", "className": "高数考研1班",
            "studentCount": 30, "totalInteractions": 120, "activeStudents": 20, "accuracy": 0.62,
            "masteryDistribution": [
                {"range": "0-60", "count": 8}, {"range": "60-80", "count": 14}, {"range": "80-100", "count": 8},
            ],
            "weakKps": [
                {"kpId": "kp021", "kpName": "洛必达法则", "avgMastery": 42, "studentCount": 18},
                {"kpId": "kp036", "kpName": "定积分的应用", "avgMastery": 48, "studentCount": 15},
            ],
            "errorStats": [
                {"errorType": "计算失误", "count": 12, "examples": ["洛必达求导漏乘"]},
                {"errorType": "概念混淆", "count": 7},
            ],
            "hotQuestions": [{"question": "洛必达法则使用条件", "count": 9}],
            "ranking": [
                {"studentId": 1, "displayName": "张三", "mastery": 88, "interactions": 15},
                {"studentId": 2, "displayName": "李四", "mastery": 45, "interactions": 9},
            ],
        }
        data = self.post("/class-analysis", payload)
        overview = data["overview"]
        self.assertEqual(overview["studentCount"], 30)
        self.assertEqual(overview["interactionCount"], 120)
        self.assertGreaterEqual(len(data["advice"]), 3)
        for item in data["advice"]:
            self.assertTrue(item["title"])
            self.assertTrue(item["content"])
            self.assertIn(item["priority"], {"HIGH", "MEDIUM", "LOW"})
        self.assertTrue(data["weakTop10"])
        self.assertTrue(data["errorSummary"])
        self.assertTrue(data["hotQuestions"])
        self.assertTrue(data["ranking"])
        self.assertTrue(data["summary"])
        self.assertIn(data["mode"], {"mock", "real"})

    # ------------------------------------------------------ AI11 /config/extract
    def test_23_config_extract_full(self):
        text = "把最大难度调到2，暂时关闭教师资料，级数先别讲"
        data = self.post("/config/extract", {"text": text, "current": {}})
        patch = data["patch"]
        self.assertEqual(patch["maxDifficulty"], 2)
        self.assertFalse(patch["kbAccess"]["kb4"])
        self.assertIn("级数", patch["disabledTopics"])
        self.assertTrue(data["explanation"])
        self.assertEqual(data["unrecognized"], [])

    def test_24_config_extract_mode_and_scope(self):
        data = self.post("/config/extract", {"text": "改成引导式，只讲第三章，难度调到3"})
        patch = data["patch"]
        self.assertEqual(patch["answerMode"], "GUIDED")
        self.assertEqual(patch["maxDifficulty"], 3)
        self.assertEqual(patch["knowledgeScope"]["mode"], "CHAPTER")

    def test_25_config_extract_unrecognized(self):
        data = self.post("/config/extract", {"text": "今天天气不错"})
        self.assertEqual(data["patch"], {})
        self.assertTrue(data["explanation"])
        self.assertTrue(data["unrecognized"])

    # ------------------------------------------------ AI12 /knowledge/documents
    def test_26_knowledge_documents(self):
        data = self.get("/knowledge/documents")
        docs = data["documents"]
        self.assertGreaterEqual(len(docs), 5)
        ids = {d["documentId"] for d in docs}
        for builtin in ("kb1-outline", "kb2-textbook", "kb3-questions", "kb4-teacher", "kb5-graph"):
            self.assertIn(builtin, ids)
        for doc in docs:
            for key in ("documentId", "name", "kb", "scope", "chunks", "enabled", "size"):
                self.assertIn(key, doc)
            self.assertIn(doc["kb"], {"KB1", "KB2", "KB3", "KB4", "KB5"})
        stats = data["stats"]
        self.assertEqual(stats["documentCount"], len(docs))
        self.assertGreater(stats["chunkCount"], 10)
        for kb in ("KB1", "KB2", "KB3", "KB4"):
            self.assertIn(kb, stats["byKb"])

    # -------------------------------------------- AI13/14/15/16 knowledge admin
    def test_27_knowledge_upload_patch_delete(self):
        name = "自动化测试-教师资料-%s.md" % uuid.uuid4().hex[:6]
        content = ("# 教师资料\n\n极限与导数教学建议。\n\n"
                   "洛必达法则使用前必须确认 0/0 或 ∞/∞ 型，并检查可导性。\n").encode("utf-8")
        files = {"file": (name, content, "text/markdown")}
        form = {"kb": "KB4", "classId": "C-TEST-01", "uploadedBy": "1"}
        resp = self.client.post("/knowledge/upload", files=files, data=form)
        self.assertEqual(resp.status_code, 200, msg=resp.text[:500])
        body = resp.json()
        doc = body["document"]
        self.assertGreaterEqual(body["chunks"], 1)
        self.assertEqual(doc["scope"], "CLASS")
        self.assertEqual(doc["classId"], "C-TEST-01")
        self.assertEqual(doc["kb"], "KB4")
        self.assertTrue(doc["enabled"])
        doc_id = doc["documentId"]
        try:
            listed = self.get("/knowledge/documents?classId=C-TEST-01")["documents"]
            self.assertIn(doc_id, {d["documentId"] for d in listed})
            patched = self.client.patch("/knowledge/documents/%s" % doc_id, json={"enabled": False})
            self.assertEqual(patched.status_code, 200)
            self.assertFalse(patched.json()["enabled"])
            patched = self.client.patch("/knowledge/documents/%s" % doc_id, json={"enabled": True})
            self.assertTrue(patched.json()["enabled"])
            deleted = self.client.delete("/knowledge/documents/%s" % doc_id)
            self.assertEqual(deleted.status_code, 200)
            again = self.client.delete("/knowledge/documents/%s" % doc_id)
            self.assertEqual(again.status_code, 404)
        finally:
            self.client.delete("/knowledge/documents/%s" % doc_id)

    def test_28_knowledge_builtin_delete_forbidden(self):
        resp = self.client.delete("/knowledge/documents/kb1-outline")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())

    def test_29_knowledge_rebuild(self):
        data = self.post("/knowledge/rebuild", {})
        self.assertGreaterEqual(data["documentCount"], 5)
        self.assertGreater(data["chunkCount"], 10)
        self.assertIsInstance(data["durationMs"], int)
        self.assertIn(data["mode"], {"mock", "real"})

    # ------------------------------------------------- AI 服务容错与降级
    def test_30_llm_json_parse_tolerance(self):
        """模型输出容错：裸 JSON、markdown 代码块、带前后缀均可解析，非法内容抛 LLMError。"""
        from app.llm import LLMError, parse_json_content

        self.assertEqual(parse_json_content('{"answer": "ok"}'), {"answer": "ok"})
        fenced = '\u0060\u0060\u0060json\n{"answer": "代码块", "kpIds": ["kp021"]}\n\u0060\u0060\u0060'
        data = parse_json_content(fenced)
        self.assertEqual(data["answer"], "代码块")
        self.assertEqual(data["kpIds"], ["kp021"])
        noisy = '说明如下：{"answer": "前后缀"} 以上。'
        self.assertEqual(parse_json_content(noisy)["answer"], "前后缀")
        with self.assertRaises(LLMError):
            parse_json_content("这不是 JSON")
        with self.assertRaises(LLMError):
            parse_json_content("")

    def test_31_real_mode_degrades_to_mock(self):
        """real 模式下 LLM 调用失败必须降级 mock，响应 200 且 mode=mock（任务 E）。"""
        from app import service
        from app.config import settings as app_settings
        from app.llm import LLMError

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json

        def boom(*_args, **_kwargs):
            raise LLMError("模拟 DeepSeek 网络异常")

        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"
            self.assertTrue(app_settings.llm_ready)
            service.llm_client.chat_json = boom
            resp = self.client.post("/qa", json=dict(QA_BASE, message="洛必达法则的使用条件是什么"))
            self.assertEqual(resp.status_code, 200, msg=resp.text[:500])
            body = resp.json()
            self.assertEqual(body["mode"], "mock")
            self.assertFalse(body["blocked"])
            self.assertTrue(body["answer"].strip())
            self.assertIn("【先判断】", body["answer"])
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key


    # ------------------------------------------- 契约 v1.1 行为矩阵补充用例
    def test_32_qa_english_soft_scope(self):
        """非数学话题（英语）走软范围：不拦截、knowledgeCovered=false、给 scopeWarning。"""
        data = self.ask("英语单词怎么背才能记住")
        self.assertFalse(data["blocked"])
        self.assertFalse(data["knowledgeCovered"])
        self.assertEqual(data["scopeWarning"], SOFT_SCOPE_WARNING)
        self.assertEqual(data["sources"], [])
        self.assertGreater(len(data["answer"]), 40)

    def test_33_qa_hard_block_matrix(self):
        """线性代数/概率/复变等超纲科目必须硬拦截且统一话术。"""
        for message in ("矩阵的特征值怎么求", "概率论期望怎么算", "复变函数留数定理"):
            data = self.ask(message)
            self.assertTrue(data["blocked"], msg=message)
            self.assertEqual(data["answer"], BLOCK_MESSAGE, msg=message)
            self.assertEqual(data["sources"], [], msg=message)
            self.assertFalse(data["knowledgeCovered"], msg=message)
            self.assertIsNone(data["scopeWarning"], msg=message)

    def test_34_qa_math_not_covered(self):
        """数学范围内但知识库无命中：如实告知并建议换问法，不设 scopeWarning。"""
        data = self.ask("戴德金分割是什么")
        self.assertFalse(data["blocked"])
        self.assertFalse(data["knowledgeCovered"])
        self.assertIsNone(data["scopeWarning"])
        self.assertEqual(data["sources"], [])
        self.assertIn("知识库暂无相关内容", data["answer"])
        self.assertIn("换一种问法", data["answer"])

    def test_35_retrieve_uploaded_class_document(self):
        """上传资料进入向量索引，且按班级隔离（其他班级检索不到）。"""
        name = "向量检索-教师资料-%s.md" % uuid.uuid4().hex[:6]
        marker = "阿姆斯极限判别法"
        content = (
            "# 教师资料\n\n"
            "洛必达法则使用前必须确认 0/0 或 ∞/∞ 型，并检查可导性。\n\n"
            f"{marker}：用于判定数列收敛的补充方法，先验证单调有界再取极限。\n"
        ).encode("utf-8")
        resp = self.client.post(
            "/knowledge/upload",
            files={"file": (name, content, "text/markdown")},
            data={"kb": "KB4", "classId": "C-VEC-01", "uploadedBy": "1"},
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text[:500])
        doc_id = resp.json()["document"]["documentId"]
        try:
            data = self.post(
                "/retrieve",
                {"query": marker, "topK": 8, "minScore": 0.15, "classId": "C-VEC-01"},
            )
            self.assertTrue(data["enough"], msg=json.dumps(data, ensure_ascii=False))
            self.assertIn(doc_id, {item["documentId"] for item in data["items"]})
            other = self.post(
                "/retrieve",
                {"query": marker, "topK": 8, "minScore": 0.15, "classId": "C-OTHER"},
            )
            self.assertNotIn(doc_id, {item["documentId"] for item in other["items"]})
        finally:
            self.client.delete("/knowledge/documents/%s" % doc_id)


    # ------------------------------------------- 契约 v1.2 新增用例
    def test_36_retrieval_integral_parts(self):
        """v1.2 §2 检索验收：∫2xe^xdx 必须召回「分部积分法」，不能落到微分方程章节。"""
        data = self.post("/retrieve", {"query": "求∫2xe^xdx", "topK": 8, "minScore": 0.15})
        self.assertTrue(data["enough"], msg=json.dumps(data, ensure_ascii=False))
        items = data["items"]
        self.assertTrue(items)
        citations = [item["citation"] for item in items]
        hit = [
            citation
            for citation in citations
            if ("第4章" in citation and "第4节" in citation and "分部积分法" in citation)
            or ("第5章" in citation and "分部积分法" in citation)
        ]
        self.assertTrue(hit, msg="未召回分部积分法：" + json.dumps(citations, ensure_ascii=False))
        kp_ids = {item["kpId"] for item in items}
        self.assertTrue(kp_ids & {"kp031", "kp035"}, msg=str(kp_ids))
        for item in items:
            self.assertTrue(item["chunkId"])
            self.assertTrue(item["chapter"])
            self.assertTrue(item["section"])
            self.assertTrue(item["citation"].startswith("《"))

    def test_37_sources_deduped(self):
        """v1.2 §2：sources 按 chunkId 去重且数量不超过 topK，与实际入库片段一一对应。"""
        data = self.post("/retrieve", {"query": "分部积分法怎么用", "topK": 8, "minScore": 0.15})
        chunk_ids = [item["chunkId"] for item in data["items"]]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)), msg=str(chunk_ids))
        self.assertLessEqual(len(chunk_ids), 8)
        qa = self.ask("求∫2xe^xdx")
        source_ids = [item["chunkId"] for item in qa["sources"]]
        self.assertEqual(len(source_ids), len(set(source_ids)), msg=str(source_ids))
        for item in qa["sources"]:
            self.assertTrue(item["citation"])
            self.assertTrue(item["chapter"])
            self.assertTrue(item["section"])

    def test_38_answer_no_internal_ids(self):
        """v1.2 §3.3：真实模型输出里的「片段 N」「chunk N」「kpNNN」必须被替换/清理。"""
        from app import service
        from app.config import settings as app_settings

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json

        raw_answer = (
            "【先判断】本题是概念题，参考片段 2 与 kp021。\n\n"
            "【思路引导】先确认 0/0 或 ∞/∞ 型。\n\n"
            "【知识点讲解】详见 chunk 3 与 documentId: kb2-textbook。\n\n"
            "【易错提醒】忽略可导性会出错。\n\n"
            "【下一步】做两道基础题巩固。"
        )

        def fake_chat(system, user, **_kwargs):
            if "terms" in system:
                return {"terms": []}
            return {"answer": raw_answer}

        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"
            service.llm_client.chat_json = fake_chat
            data = self.ask("洛必达法则的使用条件是什么")
            answer = data["answer"]
            self.assertEqual(data["mode"], "real")
            self.assertNotIn("片段 2", answer)
            self.assertNotIn("片段 2", answer.replace(" ", " "))
            self.assertNotRegex(answer, r"片段\s*\d+")
            self.assertNotRegex(answer, r"(?i)chunk\s*\d+")
            self.assertNotRegex(answer, r"kp\d{3}")
            self.assertNotIn("documentId", answer)
            self.assertIn("洛必达法则", answer)
            self.assertIn(data["sources"][0]["citation"], answer)
            self.assertIn("【参考资料】", answer)
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key

    def test_39_conversation_history(self):
        """v1.2 §3.1：history 只取最近 8 条，注入提示词并原样回传 conversationId。"""
        from app import service
        from app.config import settings as app_settings

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json
        captured = []

        def fake_chat(system, user, **_kwargs):
            captured.append(user)
            if "terms" in system:
                return {"terms": []}
            return {"answer": "【先判断】\n结合上文继续讲。\n\n【思路引导】\n1. 先看条件。\n\n"
                              "【知识点讲解】\n洛必达法则要求 0/0 或 ∞/∞ 型。\n\n"
                              "【易错提醒】\n注意可导性。\n\n【下一步】\n继续做练习。"}

        history = [
            {"role": "user", "content": "最早的历史标记甲"},
            {"role": "assistant", "content": "最早的历史标记乙"},
            {"role": "user", "content": "前面讲过极限的类型"},
            {"role": "assistant", "content": "是的，有七种未定式"},
            {"role": "user", "content": "刚才讲到洛必达法则的适用条件"},
            {"role": "assistant", "content": "适用条件是 0/0 或 ∞/∞"},
            {"role": "user", "content": "那使用前要检查什么"},
            {"role": "assistant", "content": "检查可导性与分母导数"},
            {"role": "user", "content": "还有别的注意点吗"},
            {"role": "assistant", "content": "注意验证极限存在"},
        ]
        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"
            service.llm_client.chat_json = fake_chat
            data = self.ask(
                "继续讲讲使用条件",
                conversationId="conv-v12-1",
                history=history,
            )
            self.assertEqual(data["mode"], "real")
            self.assertEqual(data["modelSource"], "system")
            self.assertEqual(data["conversationId"], "conv-v12-1")
            self.assertEqual(data["model"], service.llm_client.config.deepseek_model)
            prompt = next((text for text in captured if "【最近对话" in text), "")
            self.assertTrue(prompt)
            self.assertIn("刚才讲到洛必达法则的适用条件", prompt)
            self.assertNotIn("最早的历史标记甲", prompt)
            self.assertNotIn("最早的历史标记乙", prompt)
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key

    def test_40_user_llm_override(self):
        """v1.2 §3.1：请求级 llm 覆盖优先使用用户 key，日志与响应都不得泄露 key。"""
        from app import service
        from app.config import settings as app_settings
        from app.llm import DeepSeekClient

        original_chat = DeepSeekClient.chat_json
        secret = "sk-user-secret-v12-abc"
        records = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = CaptureHandler()
        logger = logging.getLogger("ams.ai")
        logger.addHandler(handler)

        def fake_chat(self, system, user, **_kwargs):
            if "terms" in system:
                return {"terms": []}
            return {"answer": "【先判断】\n使用用户自带模型回答。\n\n【思路引导】\n提示。\n\n"
                              "【知识点讲解】\n讲解。\n\n【易错提醒】\n提醒。\n\n【下一步】\n练习。"}

        try:
            self.assertFalse(app_settings.llm_ready)
            DeepSeekClient.chat_json = fake_chat
            payload = dict(QA_BASE, message="洛必达法则的使用条件是什么")
            payload["llm"] = {"apiKey": secret, "baseUrl": "https://example.invalid/v1", "model": "user-model"}
            resp = self.client.post("/qa", json=payload)
            self.assertEqual(resp.status_code, 200, msg=resp.text[:500])
            data = resp.json()
            self.assertEqual(data["mode"], "real")
            self.assertEqual(data["modelSource"], "user")
            self.assertEqual(data["model"], "user-model")
            self.assertTrue(data["answer"].strip())
            self.assertNotIn(secret, json.dumps(data, ensure_ascii=False))
            self.assertNotIn(secret, resp.text)
            self.assertFalse(any(secret in message for message in records), msg=str(records))
        finally:
            DeepSeekClient.chat_json = original_chat
            logger.removeHandler(handler)

    def test_41_embedding_provider_fallback(self):
        """v1.2 §1：EMBEDDING_PROVIDER=openai 但缺配置时回退 local，Health 同步暴露生效值。"""
        from app.config import settings as app_settings
        from app.embeddings import resolve_embeddings

        original = (
            app_settings.embedding_provider,
            app_settings.embedding_base_url,
            app_settings.embedding_api_key,
            app_settings.embedding_model,
        )
        try:
            app_settings.embedding_provider = "openai"
            app_settings.embedding_base_url = ""
            app_settings.embedding_api_key = ""
            app_settings.embedding_model = ""
            _embeddings, info = resolve_embeddings(provider="openai", base_url="", api_key="", model="")
            self.assertEqual(info.provider, "local")
            self.assertEqual(info.dim, 1024)
        finally:
            (
                app_settings.embedding_provider,
                app_settings.embedding_base_url,
                app_settings.embedding_api_key,
                app_settings.embedding_model,
            ) = original
        data = self.get("/health")
        self.assertIn(data["embedding_provider"], {"local", "openai"})
        self.assertTrue(data["embedding_model"])
        self.assertGreater(data["embedding_dim"], 0)
        self.assertEqual(data["retrieval_mode"], "hybrid")
        self.assertTrue(data["supports_user_key"])

    def test_42_followup_retrieval_uses_history(self):
        """v1.2 联调：短追问「你再来一个难一点的」应沿用上一轮问题做检索。"""
        history = [
            {"role": "user", "content": "求∫2xe^xdx 的积分怎么算？"},
            {"role": "assistant", "content": "这是分部积分法，令 u=x，dv=e^x dx。"},
        ]
        data = self.ask("你再来一个难一点的", conversationId="1", history=history)
        self.assertFalse(data["blocked"])
        self.assertTrue(
            data["knowledgeCovered"],
            msg=json.dumps(data, ensure_ascii=False)[:800],
        )
        sources = data["sources"]
        self.assertTrue(sources, msg="追问未召回到知识库")
        citations = [item.get("citation", "") for item in sources]
        self.assertIn("分部积分法", citations[0])
        self.assertIn("第4章", citations[0])
        self.assertIn("第4节", citations[0])
        self.assertNotIn("知识库暂无相关内容", data["answer"])
        # 历史只用于检索，不能把追问原句当成引用
        self.assertFalse(any("你再来一个难一点的" in citation for citation in citations))
        self.assertTrue(data["kpIds"])
        self.assertEqual(data["conversationId"], "1")


    def test_43_rewrite_terms_do_not_override_followup(self):
        """查询改写词只做扩展召回：注入「不定积分」等词也不能改变追问的 top1 分部积分法。"""
        from app import service
        from app.config import settings as app_settings

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json

        def fake_chat(system, user, **_kwargs):
            if "terms" in system:
                return {"terms": ["不定积分", "指数函数积分", "乘积积分"]}
            return {
                "answer": "【先判断】\n沿用上文的分部积分思路。\n\n【思路引导】\n再算一道。\n\n"
                          "【知识点讲解】\n分部积分法。\n\n【易错提醒】\n注意符号。\n\n"
                          "【下一步】\n继续练习。"
            }

        history = [
            {"role": "user", "content": "求∫2xe^xdx 的积分怎么算？"},
            {"role": "assistant", "content": "这是分部积分法，令 u=x，dv=e^x dx。"},
        ]
        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"
            service.llm_client.chat_json = fake_chat
            data = self.ask("你再来一个难一点的", conversationId="1", history=history)
            self.assertEqual(data["mode"], "real")
            self.assertTrue(data["knowledgeCovered"])
            citations = [item.get("citation", "") for item in data["sources"]]
            self.assertTrue(citations)
            self.assertIn("分部积分法", citations[0])
            self.assertIn("第4章", citations[0])
            self.assertIn("第4节", citations[0])
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key


    def test_44_blocked_uses_real_mode_without_model(self):
        """v1.2 联调：真实服务下硬拦截回复标 mode=real + modelSource=none，且不调用模型。"""
        from app import service
        from app.config import settings as app_settings

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json
        calls = []

        def fake_chat(*args, **kwargs):
            calls.append(1)
            return {"answer": "不应被调用"}

        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"
            service.llm_client.chat_json = fake_chat
            data = self.ask("矩阵特征值怎么求")
            self.assertTrue(data["blocked"])
            self.assertEqual(data["answer"], BLOCK_MESSAGE)
            self.assertEqual(data["mode"], "real")
            self.assertEqual(data["modelSource"], "none")
            self.assertEqual(data["model"], app_settings.deepseek_model)
            self.assertEqual(data["sources"], [])
            self.assertFalse(calls, msg="硬拦截不应调用大模型")
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key



    def test_45_min_score_depends_on_embedding_provider(self):
        """v1.2：语义 embedding（bge-m3 等）的无关问题基线 0.28~0.39，阈值必须区分方案。"""
        from app.config import settings as app_settings

        original = app_settings.embedding_provider
        try:
            app_settings.embedding_provider = "local"
            self.assertAlmostEqual(app_settings.effective_min_score(), app_settings.min_score)
            app_settings.embedding_provider = "openai"
            self.assertAlmostEqual(
                app_settings.effective_min_score(), app_settings.embedding_min_score
            )
            self.assertGreater(app_settings.embedding_min_score, app_settings.min_score)
        finally:
            app_settings.embedding_provider = original

    def test_46_retrieve_default_threshold_follows_scheme(self):
        """/retrieve 不传 minScore 时按当前方案阈值判定，显式传阈值时以请求为准。"""
        from app.config import settings as app_settings

        data = self.post("/retrieve", {"query": "今天天气怎么样", "topK": 3})
        self.assertIn("enough", data)
        self.assertIn("topScore", data)
        strict = self.post(
            "/retrieve", {"query": "洛必达法则的使用条件是什么？", "topK": 3, "minScore": 0.9999}
        )
        self.assertFalse(strict["enough"])
        self.assertEqual(strict["items"], [])
        self.assertAlmostEqual(app_settings.effective_min_score(), app_settings.min_score)


    # ==================================================================
    # v1.3 契约 §3：图片识别 + 教师暂缓内容前置自测（Gate）
    # ==================================================================
    def test_47_health_vision_fields(self):
        """/health 暴露识图能力三字段（未配置 key 时为 provider=none/ready=false）。"""
        data = self.get("/health")
        self.assertIn(data["vision_provider"], {"siliconflow", "none"})
        self.assertTrue(data["vision_model"])
        self.assertIsInstance(data["vision_ready"], bool)

    def test_48_vision_extract_without_key(self):
        """未配置识图 key：HTTP 恒 200，ok=false 且给出可操作的中文提示。"""
        from app.config import settings as app_settings

        original_vision_key = app_settings.vision_api_key
        original_embedding_key = app_settings.embedding_api_key
        try:
            app_settings.vision_api_key = ""
            app_settings.embedding_api_key = ""
            app_settings.vision_provider = "auto"
            resp = self.client.post(
                "/vision/extract",
                files={"file": ("题目.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            self.assertEqual(resp.status_code, 200, msg=resp.text[:400])
            data = resp.json()
            self.assertFalse(data["ok"])
            self.assertEqual(data["text"], "")
            self.assertEqual(data["provider"], "none")
            self.assertIn("VISION_API_KEY", data["message"])
        finally:
            app_settings.vision_api_key = original_vision_key
            app_settings.embedding_api_key = original_embedding_key

    def test_49_vision_extract_success_and_failure(self):
        """识图成功返回 ok=true+text；模型异常时转成 ok=false 而不是 500。"""
        from app import vision

        original_extract = vision.client.extract

        def fake_ok(image_bytes, content_type):
            self.assertEqual(content_type, "image/png")
            self.assertTrue(image_bytes)
            return "题干：求 sinx/x 的极限。"

        def fake_fail(image_bytes, content_type):
            raise vision.VisionError(vision.FAILED_MESSAGE)

        try:
            vision.client.extract = fake_ok
            resp = self.client.post(
                "/vision/extract",
                files={"file": ("a.png", b"fake-image", "image/png")},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["ok"])
            self.assertIn("sinx/x", data["text"])
            self.assertIsNone(data["message"])

            resp_bad = self.client.post(
                "/vision/extract",
                files={"file": ("a.txt", b"not-an-image", "text/plain")},
            )
            self.assertEqual(resp_bad.status_code, 200)
            bad = resp_bad.json()
            self.assertFalse(bad["ok"])
            self.assertEqual(bad["text"], "")
            self.assertIn("仅支持", bad["message"])

            vision.client.extract = fake_fail
            resp2 = self.client.post(
                "/vision/extract",
                files={"file": ("a.png", b"fake-image", "image/png")},
            )
            self.assertEqual(resp2.status_code, 200)
            data2 = resp2.json()
            self.assertFalse(data2["ok"])
            self.assertEqual(data2["text"], "")
            self.assertEqual(data2["message"], vision.FAILED_MESSAGE)
        finally:
            vision.client.extract = original_extract

    def _gate_question(self, **extra):
        conversation_id = "conv-gate-" + uuid.uuid4().hex[:6]
        payload = dict(QA_BASE)
        payload.update(
            {
                "conversationId": conversation_id,
                "message": "级数怎么判断收敛？",
                "teacherConfig": {"answerMode": "MIXED", "maxDifficulty": 3, "disabledTopics": ["级数"]},
            }
        )
        payload.update(extra)
        return conversation_id, self.ask(payload.pop("message"), **payload)

    def test_50_teacher_scope_returns_gate_quiz(self):
        """教师禁用话题：不硬拦截，返回 3 道前置单选（不含答案），且不调用大模型。"""
        from app import service
        from app.config import settings as app_settings

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json
        calls = []

        def fake_chat(*args, **kwargs):
            calls.append(1)
            return {"answer": "不应被调用", "terms": []}

        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"
            service.llm_client.chat_json = fake_chat
            conversation_id, data = self._gate_question()
            self.assertFalse(data["blocked"])
            self.assertEqual(data["action"]["type"], "GATE")
            self.assertEqual(data["action"]["label"], "前置自测")
            self.assertFalse(data["knowledgeCovered"])
            self.assertEqual(data["sources"], [])
            self.assertEqual(data["conversationId"], conversation_id)
            self.assertIn("不会直接给作业答案", data["answer"])
            gate = data["gate"]
            self.assertEqual(gate["state"], "QUIZ")
            self.assertEqual(gate["topic"], "级数")
            self.assertEqual(gate["total"], 3)
            self.assertEqual(len(gate["questions"]), 3)
            self.assertTrue(gate["prerequisites"])
            for index, question in enumerate(gate["questions"], start=1):
                self.assertEqual(question["questionId"], "gq%d" % index)
                self.assertEqual(question["index"], index)
                self.assertTrue(question["stem"])
                self.assertEqual(len(question["options"]), 4)
                self.assertLessEqual(question["difficulty"], 2)
                self.assertNotIn("answerKey", question)
                self.assertNotIn("analysis", question)
            self.assertFalse(calls, msg="前置自测出题不应调用大模型")
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key

    def test_51_gate_check_failed(self):
        """答错 2 题以上：state=FAILED、不出教学答案、sources 为空。"""
        from app.gate import gate_store

        _conversation_id, data = self._gate_question()
        gate = data["gate"]
        answers = [
            {"questionId": "gq1", "choice": "Z"},
            {"questionId": "gq2", "choice": "Z"},
            {"questionId": "gq3", "choice": "Z"},
        ]
        result = self.post(
            "/qa/gate/check",
            {"gateId": gate["gateId"], "conversationId": _conversation_id, "answers": answers},
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["state"], "FAILED")
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["score"], 0)
        self.assertTrue(result["feedback"])
        self.assertIsNone(result["teaching"])
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["sources"], [])
        self.assertFalse(result["knowledgeCovered"])
        self.assertEqual(result["gate"]["state"], "FAILED")
        record = gate_store.get(gate["gateId"])
        self.assertIsNotNone(record)

    def test_52_gate_check_passed_and_unlock(self):
        """全对通过：三步教学含「第 1/2/3 步」，同会话再问同一话题不再出测试。"""
        from app.gate import gate_store

        conversation_id, data = self._gate_question()
        gate = data["gate"]
        record = gate_store.get(gate["gateId"])
        self.assertIsNotNone(record)
        answers = [
            {"questionId": question["questionId"], "choice": question["answerKey"]}
            for question in record.questions
        ]
        result = self.post(
            "/qa/gate/check",
            {"gateId": gate["gateId"], "conversationId": conversation_id, "answers": answers},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["state"], "PASSED")
        self.assertEqual(result["score"], 3)
        self.assertIsNotNone(result["teaching"])
        titles = [step["title"] for step in result["teaching"]["steps"]]
        self.assertEqual(len(titles), 3)
        for index, key in enumerate(["第 1 步", "第 2 步", "第 3 步"]):
            self.assertIn(key, titles[index])
        self.assertTrue(result["teaching"]["practice"])
        self.assertIn("三步", result["answer"])

        # 通过后同一 conversationId 再问同话题：进入正常检索答疑（不再出 gate）
        _conversation_id2, again = self._gate_question(conversationId=conversation_id)
        self.assertIsNone(again.get("gate"))
        self.assertFalse(again["blocked"])
        self.assertTrue(again["knowledgeCovered"])
        self.assertTrue(again["sources"])

    def test_53_gate_check_expired(self):
        """gateId 不存在/过期：HTTP 200 + state=EXPIRED 的固定结构。"""
        result = self.post(
            "/qa/gate/check",
            {
                "gateId": "g-deadbeef",
                "conversationId": "conv-expired",
                "answers": [{"questionId": "gq1", "choice": "A"}],
            },
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["state"], "EXPIRED")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["feedback"], "前置测试已过期，请重新提问。")
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["sources"], [])
        self.assertFalse(result["knowledgeCovered"])
        self.assertIsNone(result["gate"])
        self.assertIsNone(result["teaching"])

    def test_54_hard_scope_has_no_gate(self):
        """课程外数学仍走硬拦截：blocked=true、无 gate、不调用模型。"""
        data = self.ask("矩阵特征值怎么求", teacherConfig={"disabledTopics": ["级数"]})
        self.assertTrue(data["blocked"])
        self.assertIsNone(data.get("gate"))
        self.assertEqual(data["answer"], BLOCK_MESSAGE)
        self.assertEqual(data["sources"], [])

    def test_55_gate_teaching_real_and_fallback(self):
        """真实模式：模型给出三步时 mode=real；模型失败时降级 mock，仍保证三步文案。"""
        from app import service
        from app.config import settings as app_settings
        from app.gate import gate_store
        from app.llm import LLMError

        original_mode = app_settings.ai_mode
        original_key = app_settings.deepseek_api_key
        original_chat = service.llm_client.chat_json

        def fake_ok(system, user, **_kwargs):
            return {
                "steps": [
                    {"title": "第 1 步：补齐前置", "content": "先复习极限与定积分。"},
                    {"title": "第 2 步：建立概念", "content": "再理解级数收敛的定义。"},
                    {"title": "第 3 步：带做一题", "content": "最后判断一道基础题，不给最终答案。"},
                ],
                "practice": "建议自测：2 道基础题。",
            }

        def fake_fail(*args, **kwargs):
            raise LLMError("模拟超时")

        try:
            app_settings.ai_mode = "auto"
            app_settings.deepseek_api_key = "sk-test"

            conversation_id, data = self._gate_question()
            record = gate_store.get(data["gate"]["gateId"])
            answers = [
                {"questionId": question["questionId"], "choice": question["answerKey"]}
                for question in record.questions
            ]

            service.llm_client.chat_json = fake_ok
            result = self.post(
                "/qa/gate/check",
                {"gateId": data["gate"]["gateId"], "conversationId": conversation_id, "answers": answers},
            )
            self.assertTrue(result["passed"])
            self.assertEqual(result["mode"], "real")
            self.assertEqual(result["modelSource"], "system")
            self.assertIn("先复习极限", result["teaching"]["steps"][0]["content"])

            service.llm_client.chat_json = fake_fail
            conversation_id2, data2 = self._gate_question()
            record2 = gate_store.get(data2["gate"]["gateId"])
            answers2 = [
                {"questionId": question["questionId"], "choice": question["answerKey"]}
                for question in record2.questions
            ]
            result2 = self.post(
                "/qa/gate/check",
                {"gateId": data2["gate"]["gateId"], "conversationId": conversation_id2, "answers": answers2},
            )
            self.assertTrue(result2["passed"])
            self.assertEqual(result2["mode"], "mock")
            self.assertEqual(result2["modelSource"], "mock")
            titles2 = [step["title"] for step in result2["teaching"]["steps"]]
            self.assertIn("第 1 步", titles2[0])
            self.assertIn("第 3 步", titles2[2])
        finally:
            service.llm_client.chat_json = original_chat
            app_settings.ai_mode = original_mode
            app_settings.deepseek_api_key = original_key


if __name__ == "__main__":
    unittest.main(verbosity=2)