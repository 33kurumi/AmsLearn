# -*- coding: utf-8 -*-
r"""v1.4.1 前置自测（Gate）持久化自测。

验证 gate 会话、判分结果与「已通过」标记确实落在 SQLite，
重新构造 GateStore（等价于 AI 服务重启）后仍可读取；TTL 过期后清理。

运行方式（工作目录 ai-service）：
    .\.venv\Scripts\python.exe -m unittest tests.test_gate_store -v
"""

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["AI_MODE"] = "mock"

from app.gate import GATE_TTL_SECONDS, GateStore  # noqa: E402


class GateStorePersistenceTest(unittest.TestCase):
    """同一 SQLite 文件重建 GateStore 后，状态不丢。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "gate.db"
        self.store = GateStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _new_store(self):
        return GateStore(self.db_path)

    def _create(self):
        return self.store.create(
            topic="级数",
            reason="教师暂缓",
            conversation_id="conv-persist",
            message="级数怎么判断收敛？",
        )

    def test_01_create_persists_across_reload(self):
        record = self._create()
        self.assertEqual(len(record.questions), 3)
        self.assertTrue(self.store.db_path.endswith("gate.db"))

        reloaded = self._new_store()
        try:
            found = reloaded.get(record.gate_id)
            self.assertIsNotNone(found)
            self.assertEqual(found.gate_id, record.gate_id)
            self.assertEqual(found.topic, "级数")
            self.assertEqual(found.conversation_id, "conv-persist")
            self.assertEqual(found.state, "QUIZ")
            self.assertEqual(len(found.questions), 3)
            self.assertEqual(found.questions[0]["stem"], record.questions[0]["stem"])
            self.assertEqual(found.questions[0]["answerKey"], record.questions[0]["answerKey"])
        finally:
            reloaded.close()

    def test_02_score_persists_across_reload(self):
        record = self._create()
        wrong_answers = [
            {"questionId": question["questionId"], "choice": "Z"}
            for question in record.questions
        ]
        result = self.store.score(record, wrong_answers)
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["passed"])

        reloaded = self._new_store()
        try:
            found = reloaded.get(record.gate_id)
            self.assertIsNotNone(found)
            self.assertEqual(found.state, "FAILED")
            self.assertEqual(found.score, 0)
        finally:
            reloaded.close()

    def test_03_passed_mark_persists_across_reload(self):
        self.assertFalse(self.store.is_passed("conv-pass", "级数"))
        self.store.mark_passed("conv-pass", "级数")
        self.assertTrue(self.store.is_passed("conv-pass", "级数"))

        reloaded = self._new_store()
        try:
            self.assertTrue(reloaded.is_passed("conv-pass", "级数"))
            self.assertFalse(reloaded.is_passed("conv-other", "级数"))
        finally:
            reloaded.close()

    def test_04_expired_gate_is_cleaned(self):
        record = self._create()
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE gates SET created_at = ? WHERE gate_id = ?",
                (time.time() - GATE_TTL_SECONDS - 10, record.gate_id),
            )
            conn.commit()
        finally:
            conn.close()

        reloaded = self._new_store()
        try:
            self.assertIsNone(reloaded.get(record.gate_id))
            self.assertEqual(
                reloaded._conn.execute("SELECT COUNT(*) FROM gates").fetchone()[0], 0
            )
        finally:
            reloaded.close()

    def test_05_expired_passed_mark_is_cleaned(self):
        self.store.mark_passed("conv-expired", "级数")
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE gate_passed SET expires_at = ? WHERE conversation_id = ?",
                (time.time() - 10, "conv-expired"),
            )
            conn.commit()
        finally:
            conn.close()

        reloaded = self._new_store()
        try:
            self.assertFalse(reloaded.is_passed("conv-expired", "级数"))
        finally:
            reloaded.close()

    def test_06_clear_removes_all_rows(self):
        self._create()
        self.store.mark_passed("conv-clear", "级数")
        self.store.clear()

        reloaded = self._new_store()
        try:
            self.assertEqual(
                reloaded._conn.execute("SELECT COUNT(*) FROM gates").fetchone()[0], 0
            )
            self.assertEqual(
                reloaded._conn.execute("SELECT COUNT(*) FROM gate_passed").fetchone()[0], 0
            )
        finally:
            reloaded.close()


if __name__ == "__main__":
    unittest.main()
