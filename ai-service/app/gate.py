"""v1.3 前置自测（Gate）服务端状态。

教师把某些知识点设为暂缓/超范围时，学生提问不再直接给讲解，而是先做 3 道
前置单选题（正确答案只保存在服务端存储里，绝不随 /qa 返回前端）。通过线 2/3；
通过后同 (conversationId, topic) 在 TTL 内不再重复弹测试。

v1.4.1：gate 会话与通过标记持久化到本地 SQLite（默认 data/gate.db），
AI 服务重启后仍可继续作答；TTL 2 小时，过期记录在读写时自动清理。
"""
from __future__ import annotations

import json
import logging
import random
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .builtin_questions import all_questions
from .config import KB_TITLES, settings
from .kp import registry as kp_registry
from .vector_store import describe_source

logger = logging.getLogger("ams.ai.gate")

GATE_TTL_SECONDS = 2 * 3600
GATE_TOTAL = 3
GATE_PASS_LINE = 2
MAX_QUESTION_DIFFICULTY = 2

GATE_ACTION = {"type": "GATE", "label": "前置自测", "params": None}


@dataclass
class GateRecord:
    gate_id: str
    topic: str
    reason: str
    conversation_id: str
    topic_kp_ids: list[str] = field(default_factory=list)
    prerequisites: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    state: str = "QUIZ"
    score: int | None = None

    @property
    def total(self) -> int:
        return len(self.questions)

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.created_at > GATE_TTL_SECONDS


_SCHEMA = """
CREATE TABLE IF NOT EXISTS gates (
    gate_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    conversation_id TEXT NOT NULL DEFAULT '',
    topic_kp_ids TEXT NOT NULL DEFAULT '[]',
    prerequisites TEXT NOT NULL DEFAULT '[]',
    questions TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'QUIZ',
    score INTEGER
);
CREATE INDEX IF NOT EXISTS idx_gates_created_at ON gates(created_at);
CREATE TABLE IF NOT EXISTS gate_passed (
    conversation_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (conversation_id, topic)
);
CREATE INDEX IF NOT EXISTS idx_gate_passed_expires ON gate_passed(expires_at);
"""


def _row_to_record(row: sqlite3.Row) -> GateRecord:
    def _loads(value: str) -> list:
        try:
            return list(json.loads(value or "[]"))
        except (TypeError, ValueError):
            return []

    return GateRecord(
        gate_id=row["gate_id"],
        topic=row["topic"],
        reason=row["reason"],
        conversation_id=row["conversation_id"],
        topic_kp_ids=_loads(row["topic_kp_ids"]),
        prerequisites=_loads(row["prerequisites"]),
        questions=_loads(row["questions"]),
        created_at=float(row["created_at"]),
        state=row["state"],
        score=row["score"],
    )


class GateStore:
    """按 gateId 保存测试与答案；按 (conversationId, topic) 记录已通过。

    v1.4.1：状态持久化到本地 SQLite（默认 ai-service/data/gate.db）。
    AI 服务重启后，未过期的 gate 仍可继续作答，已通过标记在 TTL 内继续生效；
    TTL 仍为 2 小时，过期数据在读写时顺带清理。
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        default_path = db_path or getattr(settings, "gate_db_file", None) or ":memory:"
        self._conn, self._db_path = self._open(str(default_path))

    @staticmethod
    def _open(db_path: str) -> tuple[sqlite3.Connection, str]:
        if db_path != ":memory:":
            try:
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.exception("gate 数据库目录创建失败，回退内存模式：%s", db_path)
                db_path = ":memory:"
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
            conn.row_factory = sqlite3.Row
            if db_path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn, db_path
        except sqlite3.Error:
            logger.exception("gate 数据库初始化失败，回退内存模式：%s", db_path)
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn, ":memory:"

    @property
    def db_path(self) -> str:
        return self._db_path

    # ---- 创建 -----------------------------------------------------------
    def create(
        self,
        topic: str,
        reason: str,
        conversation_id: str | int | None,
        message: str = "",
        topic_kp_ids: list[str] | None = None,
    ) -> GateRecord:
        record = GateRecord(
            gate_id="g-%08x" % random.getrandbits(32),
            topic=topic or "该知识点",
            reason=reason or "",
            conversation_id=_cid(conversation_id),
            topic_kp_ids=list(topic_kp_ids or []),
        )
        record.topic_kp_ids = record.topic_kp_ids or _topic_kp_ids(record.topic, message)
        picked = _pick_questions(record.topic_kp_ids)
        record.questions = picked["questions"]
        record.prerequisites = picked["prerequisites"]
        with self._lock:
            self._purge_locked()
            self._conn.execute(
                "INSERT INTO gates (gate_id, topic, reason, conversation_id,"
                " topic_kp_ids, prerequisites, questions, created_at, state, score)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.gate_id,
                    record.topic,
                    record.reason,
                    record.conversation_id,
                    json.dumps(record.topic_kp_ids, ensure_ascii=False),
                    json.dumps(record.prerequisites, ensure_ascii=False),
                    json.dumps(record.questions, ensure_ascii=False),
                    record.created_at,
                    record.state,
                    record.score,
                ),
            )
            self._conn.commit()
        return record

    # ---- 查询 -----------------------------------------------------------
    def get(self, gate_id: str) -> GateRecord | None:
        with self._lock:
            self._purge_locked()
            row = self._conn.execute(
                "SELECT * FROM gates WHERE gate_id = ?", (gate_id or "",)
            ).fetchone()
            if row is None:
                return None
            record = _row_to_record(row)
            if record.expired():
                self._conn.execute(
                    "DELETE FROM gates WHERE gate_id = ?", (record.gate_id,)
                )
                self._conn.commit()
                return None
            return record

    def is_passed(self, conversation_id: str | int | None, topic: str) -> bool:
        with self._lock:
            self._purge_locked()
            row = self._conn.execute(
                "SELECT 1 FROM gate_passed"
                " WHERE conversation_id = ? AND topic = ? AND expires_at > ?",
                (_cid(conversation_id), topic or "", time.time()),
            ).fetchone()
            return row is not None

    def mark_passed(self, conversation_id: str | int | None, topic: str) -> None:
        with self._lock:
            self._purge_locked()
            self._conn.execute(
                "INSERT INTO gate_passed (conversation_id, topic, expires_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(conversation_id, topic)"
                " DO UPDATE SET expires_at = excluded.expires_at",
                (_cid(conversation_id), topic or "", time.time() + GATE_TTL_SECONDS),
            )
            self._conn.commit()

    # ---- 判分 -----------------------------------------------------------
    def score(self, record: GateRecord, answers: list[dict]) -> dict:
        answer_map = {}
        for item in answers or []:
            qid = str((item or {}).get("questionId") or "").strip()
            if qid:
                answer_map[qid] = str((item or {}).get("choice") or "").strip().upper()
        correct = 0
        wrong: list[dict] = []
        for question in record.questions:
            given = answer_map.get(question["questionId"], "")
            right = str(question.get("answerKey") or "").strip().upper()
            if given and given == right:
                correct += 1
            else:
                wrong.append(
                    {
                        "kpId": question.get("kpId"),
                        "kpName": question.get("kpName"),
                        "yourChoice": given,
                        "correctChoice": right,
                    }
                )
        total = record.total or GATE_TOTAL
        passed = correct >= GATE_PASS_LINE
        state = "PASSED" if passed else "FAILED"
        with self._lock:
            self._conn.execute(
                "UPDATE gates SET score = ?, state = ? WHERE gate_id = ?",
                (correct, state, record.gate_id),
            )
            self._conn.commit()
            record.score = correct
            record.state = state
        return {
            "score": correct,
            "total": total,
            "passed": passed,
            "wrong": wrong,
            "weakKpNames": _unique([w["kpName"] for w in wrong if w.get("kpName")]),
        }

    # ---- 内部 -----------------------------------------------------------
    def _purge_locked(self) -> None:
        now = time.time()
        self._conn.execute(
            "DELETE FROM gates WHERE created_at <= ?", (now - GATE_TTL_SECONDS,)
        )
        self._conn.execute(
            "DELETE FROM gate_passed WHERE expires_at <= ?", (now,)
        )
        # 即使没有过期行也提交：DELETE 会隐式开启写事务，不提交会一直持有锁，
        # 导致另一个 GateStore 实例（或重启前的旧进程）读写时 database is locked。
        self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM gates")
            self._conn.execute("DELETE FROM gate_passed")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _cid(conversation_id: str | int | None) -> str:
    return "" if conversation_id is None else str(conversation_id).strip()


def _unique(items: list) -> list:
    seen: set = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _all_kps() -> list:
    return kp_registry.all()


def _topic_kp_ids(topic: str, message: str = "") -> list[str]:
    """主题对应的知识点：先按消息匹配，再按主题词匹配。"""
    ids: list[str] = []
    if message:
        ids = kp_registry.match(message, 3)
    if not ids and topic:
        ids = kp_registry.match(topic, 3)
    return _unique(ids)


def _question_pool() -> list[dict]:
    """前置测试可用题：单选、有选项与答案、难度 <= 2。"""
    pool = []
    for item in all_questions():
        if (
            item.get("type") == "SINGLE"
            and item.get("options")
            and item.get("answerKey")
            and int(item.get("difficulty") or 1) <= MAX_QUESTION_DIFFICULTY
        ):
            pool.append(item)
    return pool


def _pick_questions(topic_kp_ids: list[str]) -> dict:
    """优先取主题之前（同章前一节亦可）的 2~3 个前置 kp，各出 1 道单选。"""
    kps = _all_kps()
    order = {kp.kp_id: index for index, kp in enumerate(kps)}
    topic_ids = [kp_id for kp_id in topic_kp_ids if kp_id in order]
    start = min(order[kp_id] for kp_id in topic_ids) if topic_ids else 0
    predecessor_ids = [kp.kp_id for kp in kps[:start] if kp.kp_id not in topic_ids]
    # 越靠近主题的前置 kp 越直接：从主题往前找，每个前置 kp 只出 1 道
    candidates = list(reversed(predecessor_ids))

    pool = _question_pool()
    by_kp: dict[str, list[dict]] = {}
    for item in pool:
        if item.get("kpId") not in topic_ids:
            by_kp.setdefault(item.get("kpId"), []).append(item)

    chosen: list[dict] = []
    prerequisites: list[dict] = []
    used_qids: set[str] = set()
    for kp_id in candidates:
        if len(chosen) >= GATE_TOTAL:
            break
        item = next(
            (q for q in by_kp.get(kp_id, []) if q.get("qid") not in used_qids), None
        )
        if item is None:
            continue
        chosen.append(item)
        used_qids.add(item.get("qid"))
        prerequisites.append(_prerequisite(kp_id))

    # 主题之前完全没有可用题时，才用其他非主题知识点补足
    if len(chosen) < GATE_TOTAL:
        for item in pool:
            if len(chosen) >= GATE_TOTAL:
                break
            if item.get("qid") in used_qids or item.get("kpId") in topic_ids:
                continue
            chosen.append(item)
            used_qids.add(item.get("qid"))
            if not any(p["kpId"] == item.get("kpId") for p in prerequisites):
                prerequisites.append(_prerequisite(item.get("kpId")))

    questions = []
    for index, item in enumerate(chosen[:GATE_TOTAL], start=1):
        kp_id = item.get("kpId") or ""
        questions.append(
            {
                "questionId": "gq%d" % index,
                "index": index,
                "kpId": kp_id,
                "kpName": kp_registry.name(kp_id, kp_id),
                "difficulty": int(item.get("difficulty") or 1),
                "stem": item.get("stem") or "",
                "options": [
                    {"key": str(opt.get("key") or ""), "text": str(opt.get("text") or "")}
                    for opt in item.get("options") or []
                ],
                "answerKey": str(item.get("answerKey") or ""),
                "sourceQuestionId": item.get("qid") or "",
            }
        )
    return {"questions": questions, "prerequisites": prerequisites[:GATE_TOTAL]}


def _prerequisite(kp_id: str) -> dict:
    info = describe_source(kp_id, KB_TITLES.get("KB2", "高等数学教材讲义"))
    return {
        "kpId": kp_id,
        "kpName": info.get("kpName") or kp_registry.name(kp_id, kp_id),
        "citation": info.get("citation") or "",
    }


def record_to_vo(record: GateRecord, include_answers: bool = False) -> dict:
    """转成前端可用的 gate 结构；默认剔除 answerKey。"""
    questions = []
    for item in record.questions:
        question = {
            "questionId": item.get("questionId"),
            "index": item.get("index"),
            "kpId": item.get("kpId"),
            "kpName": item.get("kpName"),
            "difficulty": item.get("difficulty"),
            "stem": item.get("stem"),
            "options": item.get("options") or [],
        }
        if include_answers:
            question["answerKey"] = item.get("answerKey")
        questions.append(question)
    return {
        "gateId": record.gate_id,
        "topic": record.topic,
        "state": record.state,
        "reason": record.reason,
        "message": "通过后我会用三步带你学会「%s」。" % record.topic,
        "prerequisites": record.prerequisites,
        "questions": questions,
        "score": record.score,
        "total": record.total,
    }


def gate_intro(topic: str) -> str:
    return (
        "这道题涉及「%s」，属于教师配置的暂缓内容。"
        "我先用 %d 道前置小题确认基础；通过后我会用三步带你学会它，不会直接给作业答案。"
        % (topic, GATE_TOTAL)
    )


gate_store = GateStore()
