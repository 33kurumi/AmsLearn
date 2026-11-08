r"""向量检索命令行演示（提交材料截图用）。

用法（在 ai-service 目录下执行）：
    .venv\Scripts\python.exe scripts\vector_demo.py                # 重建索引并演示默认问题
    .venv\Scripts\python.exe scripts\vector_demo.py 洛必达 泰勒    # 自定义问题

演示内容：
1) 导入 5 份内置知识库文档，打印文档数 / 分块数；
2) 重建 LangChain 向量索引，打印向量维度 / 向量条数 / 耗时；
3) 对每个问题打印 Top-K 命中片段的 KB、章节引用（citation）、相似度分数。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import service  # noqa: E402
from app.config import settings  # noqa: E402
from app.vector_store import vector_index  # noqa: E402

DEFAULT_QUERIES = [
    "洛必达法则的使用条件是什么",
    "泰勒公式怎么展开",
    "定积分的几何意义",
    "今天天气怎么样",
    "矩阵特征值怎么求",
]


def main(argv: list[str]) -> int:
    started = time.perf_counter()
    stats = service.ensure_ready()
    kb_stats = service.kb.stats()
    print("=" * 74)
    print("知识库导入")
    print(f"  文档数        : {kb_stats['documentCount']}")
    print(f"  分块数        : {kb_stats['chunkCount']}")
    print(f"  byKb          : {kb_stats['byKb']}")
    print("向量索引")
    print(f"  向量库        : {vector_index.info()['vectorStore']}")
    print(f"  embedding     : {vector_index.info()['embedding']}")
    print(f"  向量维度      : {vector_index.info()['vectorDim']}")
    print(f"  向量条数      : {vector_index.info()['vectorCount']}")
    print(f"  重建耗时      : {stats.get('durationMs', 0)} ms")
    print(f"  索引清单      : {settings.data_dir / 'vector_index.json'}")
    print("=" * 74)

    queries = [" ".join(argv)] if argv else DEFAULT_QUERIES
    for query in queries:
        result = vector_index.search(query, top_k=3)
        print()
        print(f"问题：{query}")
        print(f"  enough={result.enough} topScore={result.top_score} kpIds={result.kp_ids}")
        for index, item in enumerate(result.items, 1):
            print(f"  [{index}] score={item['score']:.4f} {item['kb']} {item['title']} 引用：{item['citation']}")
            print(f"      {item['excerpt'][:120]}")
    print()
    print(f"总耗时 {(time.perf_counter() - started):.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
