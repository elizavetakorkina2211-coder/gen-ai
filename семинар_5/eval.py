"""
Мини-оценка: 4 вопроса, проверяем:
1. Что агент завершает работу за разумное число шагов.
2. Что в трассе шагов есть ожидаемые инструменты.
3. Что в финальном ответе упомянуты ожидаемые ключевые числа (опционально).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import CACHE_STATS, run_agent

CASES = [
    {
        "id": 1,
        "query": "Какая сегодня ключевая ставка ЦБ?",
        "expected_tools": ["get_key_rate"],
        "must_have": [],  # число не фиксируем — зависит от живого запроса
        "comment": "Базовый тест — один инструмент, одно число.",
    },
    {
        "id": 2,
        "query": "Сколько стоит доллар сегодня и сколько стоил 1 января 2022?",
        "expected_tools": ["get_fx_rate"],
        "must_have": [],
        "comment": "Два вызова одного инструмента с разными аргументами.",
    },
    {
        "id": 3,
        "query": "Какая сейчас реальная ключевая ставка? (номинальная минус инфляция г/г)",
        "expected_tools": ["get_key_rate", "get_inflation", "calculate"],
        "must_have": ["%"],
        "comment": "Три разных инструмента + арифметика. Классический многостадийный кейс.",
    },
    {
        "id": 4,
        "query": "Посчитай, за сколько лет удвоится вклад 100 тыс руб при текущей ключевой ставке (формула 72).",
        "expected_tools": ["get_key_rate", "calculate"],
        "must_have": ["год"],
        "comment": "Вычисление с формулой: 72 / ставка = годы.",
    },
    # ----- ДЗ: +6 своих вопросов -----
    # --- 2 вопроса требуют новый инструмент compare_periods ---
    {
        "id": 5,
        "query": "Во сколько раз вырос курс доллара с января 2022 по апрель 2026?",
        "expected_tools": ["compare_periods"],
        "must_have": [],
        "comment": "compare_periods(metric=fx_USD): нужен ratio = b/a одним вызовом.",
    },
    {
        "id": 6,
        "query": "На сколько процентных пунктов изменилась ключевая ставка с декабря 2021 по март 2026?",
        "expected_tools": ["compare_periods"],
        "must_have": [],
        "comment": "compare_periods(metric=key_rate): нужен delta = b-a, а не ratio.",
    },
    # --- 2 трудных: агент может ошибиться ---
    {
        "id": 7,
        "query": "Какая была инфляция в 2023 году?",
        "expected_tools": ["get_inflation"],
        "must_have": ["%"],
        "comment": (
            "ТРУДНЫЙ: год без месяца. get_inflation требует month, агент должен "
            "сам довыбрать (обычно декабрь). Но «инфляция за 2023» неоднозначна: "
            "декабрь-к-декабрю (7.42) vs среднегодовая — модель может взять не тот месяц."
        ),
    },
    {
        "id": 8,
        "query": "Какая сейчас безработица в России?",
        "expected_tools": ["get_unemployment"],
        "must_have": ["%"],
        "comment": (
            "ТРУДНЫЙ: лаг публикации. На текущий месяц данных в CSV ещё нет, "
            "get_unemployment вернёт {'error': ...}. Агент должен откатиться на "
            "последний доступный месяц или честно сказать, а не выдумать число."
        ),
    },
    # --- 2 реальных макро-вопроса ---
    {
        "id": 9,
        "query": "Какой сейчас индекс нищеты (инфляция плюс безработица)?",
        "expected_tools": ["get_inflation", "get_unemployment", "calculate"],
        "must_have": ["%"],
        "comment": "Реальный: два индикатора Росстата + сложение через calculate.",
    },
    {
        "id": 10,
        "query": "Какая реальная доходность годового вклада под текущую ключевую ставку с поправкой на инфляцию?",
        "expected_tools": ["get_key_rate", "get_inflation", "calculate"],
        "must_have": ["%"],
        "comment": "Реальный: ставка − инфляция через формулу Фишера, считается calculate.",
    },
]


def run_case(case: dict, *, use_cache: bool = False, track_cost: bool = False) -> dict:
    print(f"\n{'=' * 70}\n[Q{case['id']}] {case['query']}\n{'-' * 70}")
    res = run_agent(
        case["query"],
        max_iter=8,
        verbose=True,
        use_cache=use_cache,
        track_cost=track_cost,
    )
    used_tools = [e["call"] for e in res["trace"] if "call" in e]
    answer = res.get("answer") or ""

    tool_match = all(t in used_tools for t in case["expected_tools"])
    text_match = all(s.lower() in answer.lower() for s in case["must_have"])
    ok = bool(answer) and tool_match and text_match

    print(f"\n  tools used : {used_tools}")
    print(
        f"  expected    : {case['expected_tools']}  → {'OK' if tool_match else 'MISS'}"
    )
    print(f"  answer      : {answer[:200]}")
    print(f"  must_have   : {case['must_have']}  → {'OK' if text_match else 'MISS'}")
    print(f"  verdict     : {'PASS' if ok else 'FAIL'}")

    return {
        "id": case["id"],
        "query": case["query"],
        "ok": ok,
        "tools_used": used_tools,
        "steps": res["steps"],
        "answer": answer,
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Мини-оценка макро-агента")
    ap.add_argument(
        "--cache",
        action="store_true",
        help="Блок 9: общий кэш инструментов на все вопросы — видно повторные вызовы",
    )
    ap.add_argument(
        "--cost",
        action="store_true",
        help="Блок 10: показать токены и стоимость по шагам",
    )
    a = ap.parse_args()

    if a.cache:
        CACHE_STATS["hits"] = CACHE_STATS["misses"] = 0

    results = [run_case(c, use_cache=a.cache, track_cost=a.cost) for c in CASES]
    passed = sum(1 for r in results if r["ok"])

    print(f"\n{'=' * 70}\nИтого: {passed}/{len(CASES)} пройдено")
    for r in results:
        mark = "[OK]  " if r["ok"] else "[FAIL]"
        print(f"  {mark} Q{r['id']} ({r['steps']} шагов) — {r['query'][:60]}")

    if a.cache:
        h, m = CACHE_STATS["hits"], CACHE_STATS["misses"]
        print(
            f"\n[кэш] на {len(CASES)} вопросах: {h} попаданий из {h + m} обращений "
            f"к инструментам — столько вызовов ЦБ/Росстата сэкономлено."
        )

    out = Path(__file__).parent / "eval_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nРезультаты: {out}")


if __name__ == "__main__":
    main()
