"""
Eval по gold-вопросам. Две метрики на уровне документа-источника:

  hit@K       — попал ли ХОТЯ БЫ ОДИН чанк из gold_sources в топ-K
                (для multi-hop — доля найденных источников).
  precision@K — какая ДОЛЯ топ-K чанков пришла из правильных источников.
                Именно она показывает «чистоту» ретрива и хорошо разводит
                стратегии чанкинга: грубые чанки тащат в топ много мусора.

Команды:
    python eval.py                      # HYBRID (dense + BM25 + RRF), k=5
    python eval.py --dense-only         # только семантический поиск
    python eval.py --dense-only --k 5   # честный dense-поиск, топ-5
    python eval.py --k 3                # сузить окно до топ-3
"""

import argparse
import json
from pathlib import Path

from pipeline import collection, hybrid_retrieve, retrieve

GOLD_PATH = Path(__file__).parent / "data" / "gold.json"


def load_gold() -> list[dict]:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def hit_rate(retrieved_ids: list[str], gold_sources: list[str]) -> float:
    """Доля gold_sources, попавших в топ-K (на уровне документа)."""
    retrieved_sources = {rid.split("__")[0] for rid in retrieved_ids}
    found = [g for g in gold_sources if g in retrieved_sources]
    return len(found) / len(gold_sources)


def precision_at_k(retrieved_ids: list[str], gold_sources: list[str]) -> float:
    """Доля чанков в топ-K, пришедших из правильных источников."""
    if not retrieved_ids:
        return 0.0
    gold = set(gold_sources)
    good = sum(1 for rid in retrieved_ids if rid.split("__")[0] in gold)
    return good / len(retrieved_ids)


def dense_only_retrieve(query: str, k: int = 5) -> dict:
    """Чистый семантический поиск в ChromaDB, ровно k результатов."""
    return collection.query(query_texts=[query], n_results=k)


def run(dense_only: bool = False, k: int = 5, verbose: bool = True) -> dict:
    gold = load_gold()
    total_hit = 0.0
    total_prec = 0.0
    results = []

    if dense_only:
        fn = lambda q: dense_only_retrieve(q, k=k)
        label = "DENSE-ONLY"
    else:
        fn = lambda q: hybrid_retrieve(q, k=k, top=max(k, 15))
        label = "HYBRID (DENSE + BM25 + RRF)"
    print(f"\n==={label}, k={k}===\n")

    for item in gold:
        q = item["question"]
        gold_sources = item["gold_sources"]

        hits = fn(q)
        retrieved_ids = hits["ids"][0][:k]
        retrieved_sources = [rid.split("__")[0] for rid in retrieved_ids]

        hit = hit_rate(retrieved_ids, gold_sources)
        prec = precision_at_k(retrieved_ids, gold_sources)
        total_hit += hit
        total_prec += prec

        results.append(
            {
                "id": item["id"],
                "type": item["type"],
                "hit": hit,
                "precision": prec,
                "gold": gold_sources,
                "retrieved_sources": retrieved_sources,
            }
        )

        if verbose:
            mark = "✓" if hit == 1.0 else ("◐" if hit > 0 else "✗")
            print(
                f"  [{item['id']:2d}] {item['type']:12s}  "
                f"hit@{k}={hit:.2f}  prec@{k}={prec:.2f}  {mark}  {q}"
            )
            print(f"         gold={gold_sources}  ->  нашли={retrieved_sources}")

    mean_hit = total_hit / len(gold)
    mean_prec = total_prec / len(gold)
    if verbose:
        print(
            f"\n  ИТОГО: hit-rate@{k} = {mean_hit:.2f}   "
            f"precision@{k} = {mean_prec:.2f}   ({len(gold)} вопросов)"
        )
    return {"hit": mean_hit, "precision": mean_prec, "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dense-only", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if collection.count() == 0:
        print("⚠ Коллекция пустая. Запусти: python pipeline.py ingest")
        return

    run(dense_only=args.dense_only, k=args.k, verbose=not args.quiet)


if __name__ == "__main__":
    main()
