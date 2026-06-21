"""
Оценка silicon sampling: сравниваем синтетические ответы (output/answers.jsonl)
с реальными ответами тех же людей (input/ground_truth.jsonl).

Метрики:
  ПРАВИЛЬНОСТЬ
    - exact_match    — доля точных совпадений кода ответа
    - within_1       - доля ответов, отстоящих от реального не более чем на 1 по шкале
    - mae_by_q       — средняя абсолютная ошибка по каждому вопросу
    - dist_gap       — |среднее_LLM − среднее_люди| по вопросу (сдвиг распределения)
  ПУТЬ / НАДЁЖНОСТЬ
    - scale_errors   — сколько ответов вне шкалы (пойманные галлюцинации)
    - halluc_reason  — сколько обоснований судья пометил как выдуманные
    - incoherent     — сколько ответов судья счёл несогласованными с профилем
    - ambiguous_qs   — сколько (персона,вопрос) интервьюер пометил двусмысленными

Выход:
  output/eval_table.csv   — построчная таблица
  output/results.json     — сводные метрики
  печать сводки в консоль

Запуск:  python eval.py
"""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict

import pandas as pd

from config import INPUT_DIR, OUTPUT_DIR, SURVEY_QUESTIONS


def _read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def main():
    answers = _read_jsonl(OUTPUT_DIR / "answers.jsonl")
    truth_rows = _read_jsonl(INPUT_DIR / "ground_truth.jsonl")
    truth = {r["respondent_id"]: r["answers"] for r in truth_rows}

    rows = []
    llm_vals = defaultdict(list)
    human_vals = defaultdict(list)
    scale_errors = halluc = incoherent = ambiguous = 0

    for a in answers:
        rid, qid = a["respondent_id"], a["question_id"]
        real = truth.get(rid, {}).get(qid)
        pred = a.get("answer_value")
        if a.get("scale_error"):
            scale_errors += 1
        if a.get("hallucinated_reasoning"):
            halluc += 1
        if a.get("coherent") is False:
            incoherent += 1
        if a.get("ambiguous"):
            ambiguous += 1

        exact = within1 = None
        if pred is not None and real is not None:
            exact = int(pred == real)
            within1 = int(abs(pred - real) <= 1)
            llm_vals[qid].append(pred)
            human_vals[qid].append(real)
        rows.append({"respondent_id": rid, "question_id": qid,
                     "llm": pred, "human": real,
                     "exact": exact, "within1": within1,
                     "ambiguous": a.get("ambiguous"),
                     "coherent": a.get("coherent"),
                     "halluc": a.get("hallucinated_reasoning")})

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "eval_table.csv", index=False)

    scored = df.dropna(subset=["exact"])
    n = len(scored)
    exact_match = round(scored["exact"].mean(), 3) if n else None
    within_1 = round(scored["within1"].mean(), 3) if n else None

    mae_by_q, dist_gap = {}, {}
    for q in SURVEY_QUESTIONS:
        if llm_vals[q]:
            pairs = list(zip(llm_vals[q], human_vals[q]))
            mae_by_q[q] = round(st.mean(abs(l - h) for l, h in pairs), 3)
            dist_gap[q] = round(abs(st.mean(llm_vals[q]) - st.mean(human_vals[q])), 3)

    results = {
        "n_scored": n,
        "exact_match": exact_match,
        "within_1": within_1,
        "mae_by_question": mae_by_q,
        "distribution_gap_by_question": dist_gap,
        "scale_errors_caught": scale_errors,
        "hallucinated_reasoning": halluc,
        "incoherent_answers": incoherent,
        "ambiguous_flags": ambiguous,
        "total_items": len(df),
    }
    (OUTPUT_DIR / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"Оценено пар (есть и LLM, и человек): {n}")
    print(f"Exact match : {exact_match}")
    print(f"Within ±1   : {within_1}")
    print(f"MAE по вопросам         : {mae_by_q}")
    print(f"Сдвиг среднего (LLM−люди): {dist_gap}")
    print("-" * 60)
    print(f"Ошибки шкалы (галлюцинации) : {scale_errors}")
    print(f"Выдуманные обоснования      : {halluc}")
    print(f"Несогласованные с профилем  : {incoherent}")
    print(f"Двусмысленные (интервьюер)  : {ambiguous}")
    print("=" * 60)
    print(f"Таблица → output/eval_table.csv | сводка → output/results.json")


if __name__ == "__main__":
    main()
