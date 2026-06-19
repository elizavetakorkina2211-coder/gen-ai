"""
Eval мульти-агента С6: 6 вопросов × 3 конфигурации.

Конфигурации:
  1) single      — одиночный агент С5 (agent_s5.run_agent)
  2) pwc         — PWC-цикл БЕЗ валидатора схемы
  3) pwc+val     — PWC-цикл С валидатором схемы

Проверяем на каждом прогоне:
  - вызван ли calculate там, где нужна арифметика (needs_calculate);
  - нет ли галлюцинаций инструментов (в трейсе И в плане);
  - есть ли в ответе обязательные подстроки (must_have_keywords).

Прогон N раз, доля успешных. Результат → eval_pwc_results.json.

Запуск:
    python eval_pwc.py            # полный прогон, N=5  (~6*3*5 = 90 запусков)
    python eval_pwc.py --single   # по одному прогону (быстрая проверка)
    python eval_pwc.py -n 3       # N=3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_s5 import run_agent
from orchestrator import run_pwc


CASES = [
    # ----- Базовые Q1-Q3 (как на семинаре) -----
    {
        "id": "Q1",
        "query": "Во сколько раз USD подорожал с 1 января 2022 по сегодня?",
        "comment": (
            "Класс ошибки C: одиночный часто считает в уме, не зовёт calculate. "
            "Также два курса (на 2022-01-01 и сегодня) независимы → естественная "
            "параллельность на 2 подвопроса."
        ),
        "needs_calculate": True,
        "must_have_keywords": ["раз", "usd"],
    },
    {
        "id": "Q2",
        "query": (
            "Какая сейчас реальная ключевая ставка, если инфляцию брать "
            "по последнему доступному месяцу, а не по году?"
        ),
        "comment": (
            "Класс ошибки B: одиночный не умеет искать «последний доступный» "
            "месяц, зацикливается. PWC должен разбить на шаги."
        ),
        "needs_calculate": True,
        "must_have_keywords": ["%"],
    },
    {
        "id": "Q3",
        "query": (
            "Какова накопленная инфляция с января 2022 по март 2026? "
            "Рассчитай как произведение всех (1 + ипц_м/100) по месяцам."
        ),
        "comment": (
            "Класс ошибки D: требует get_inflation за много месяцев + большое "
            "calculate. Планировщик соблазняется выдумать get_cumulative_inflation. "
            "Без валидатора план галлюцинирует; валидатор форсирует честный план."
        ),
        "needs_calculate": True,
        "must_have_keywords": ["%"],
    },

    # ----- Q4: ГАРАНТИРОВАННО чинится валидатором -----
    {
        "id": "Q4",
        "query": (
            "Каков среднегодовой темп роста (CAGR) курса доллара "
            "с 1 января 2022 по 1 января 2025?"
        ),
        "comment": (
            "Класс ошибки C на сложной (степенной) арифметике CAGR. Изначально "
            "задумывался как магнит галлюцинации (get_cagr), но DeepSeek-v4 "
            "дисциплинирован: инструменты не выдумывает, планирует честно "
            "get_fx_rate×2 + calculate((end/start)**(1/3)-1). Поэтому строка "
            "показывает не починку валидатором (pwc == pwc+val), а разрыв "
            "single vs PWC: одиночный склонен считать степень в уме без calculate."
        ),
        "needs_calculate": True,
        "must_have_keywords": ["%"],
    },

    # ----- Q5: естественная параллельность (3+ независимых подвопроса) -----
    {
        "id": "Q5",
        "query": "Каков суммарный курс корзины USD + EUR + CNY к рублю на сегодня?",
        "comment": (
            "Три независимых get_fx_rate (USD, EUR, CNY) на одном уровне → "
            "параллелятся; calculate(сумма) сверху. На этом вопросе меряем "
            "ускорение из части 2."
        ),
        "needs_calculate": True,
        "must_have_keywords": ["руб"],
    },

    # ----- Q6: реальный личный макро-вопрос -----
    {
        "id": "Q6",
        "query": "Во сколько раз юань (CNY) подорожал к рублю с 1 января 2022 по сегодня?",
        "comment": (
            "Личный интерес: после 2022 рубль всё сильнее завязан на юань. "
            "Структурно как Q1 (два курса + calculate), но другая валюта."
        ),
        "needs_calculate": True,
        "must_have_keywords": ["раз"],
    },
]


VALID_TOOL_NAMES = {"get_fx_rate", "get_key_rate", "get_inflation", "calculate"}


def _check_single(case: dict, result: dict) -> dict:
    used = {e["call"] for e in result.get("trace", []) if "call" in e}
    ans = (result.get("answer") or "").lower()
    hallucinated = used - VALID_TOOL_NAMES
    must = all(kw.lower() in ans for kw in case["must_have_keywords"])
    arith_without_calc = (
        case.get("needs_calculate", False)
        and "calculate" not in used
        and bool(ans)
    )
    ok = bool(ans) and not hallucinated and must and not arith_without_calc
    return {
        "ok": ok,
        "used_tools": sorted(used),
        "hallucinated": sorted(hallucinated),
        "must_have_ok": must,
        "arith_without_calc": arith_without_calc,
        "answer_preview": (result.get("answer") or "")[:180],
    }


def _check_pwc(case: dict, result: dict) -> dict:
    used = set()
    for t in result.get("trace", []):
        if t.get("kind") == "worker":
            used.update(t.get("used_tools") or [])
    ans = (result.get("answer") or "").lower()
    hallucinated = used - VALID_TOOL_NAMES

    plan_tools = set()
    plan = result.get("plan")
    if plan is not None:
        for sq in plan.subquestions:
            plan_tools.update(sq.expected_tools)
    plan_hallucinated = plan_tools - VALID_TOOL_NAMES

    must = all(kw.lower() in ans for kw in case["must_have_keywords"])
    ok = (
        bool(result.get("answer"))
        and not hallucinated
        and not plan_hallucinated
        and must
    )
    return {
        "ok": ok,
        "used_tools": sorted(used),
        "plan_tools": sorted(plan_tools),
        "hallucinated_in_workers": sorted(hallucinated),
        "hallucinated_in_plan": sorted(plan_hallucinated),
        "must_have_ok": must,
        "iterations": result.get("iterations", -1),
        "answer_preview": (result.get("answer") or "")[:180],
    }


def run_case(case: dict, *, n: int = 5) -> dict:
    single = {"runs": [], "pass": 0}
    pwc = {"runs": [], "pass": 0}        # без валидатора
    pwc_val = {"runs": [], "pass": 0}    # с валидатором

    for _ in range(n):
        # --- 1) Одиночный агент С5 ---
        try:
            r1 = run_agent(case["query"], max_iter=8, verbose=False)
        except Exception as e:
            r1 = {"answer": None, "error": f"{type(e).__name__}: {e}", "trace": []}
        c1 = _check_single(case, r1)
        single["runs"].append(c1)
        single["pass"] += int(c1["ok"])

        # --- 2) PWC без валидатора ---
        try:
            r2 = run_pwc(case["query"], max_iter=3, verbose=False, use_validator=False)
        except Exception as e:
            r2 = {"answer": None, "error": f"{type(e).__name__}: {e}",
                  "trace": [], "plan": None}
        c2 = _check_pwc(case, r2)
        pwc["runs"].append(c2)
        pwc["pass"] += int(c2["ok"])

        # --- 3) PWC + валидатор ---
        try:
            r3 = run_pwc(case["query"], max_iter=3, verbose=False, use_validator=True)
        except Exception as e:
            r3 = {"answer": None, "error": f"{type(e).__name__}: {e}",
                  "trace": [], "plan": None}
        c3 = _check_pwc(case, r3)
        pwc_val["runs"].append(c3)
        pwc_val["pass"] += int(c3["ok"])

    return {
        "id": case["id"],
        "query": case["query"],
        "comment": case["comment"],
        "n": n,
        "single": single,
        "pwc": pwc,
        "pwc_val": pwc_val,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--single", action="store_true",
                    help="Только один прогон каждого кейса (быстро)")
    ap.add_argument("-n", type=int, default=5,
                    help="Сколько прогонов на кейс (default=5)")
    args = ap.parse_args()
    n = 1 if args.single else args.n

    print(f"Eval С6: {len(CASES)} кейсов × 3 конфигурации × {n} прогонов "
          f"= {len(CASES) * 3 * n} запусков\n")
    results = []
    for case in CASES:
        print(f"=== {case['id']}: {case['query'][:70]}...")
        r = run_case(case, n=n)
        results.append(r)
        print(f"   single: {r['single']['pass']}/{n}   "
              f"pwc: {r['pwc']['pass']}/{n}   "
              f"pwc+val: {r['pwc_val']['pass']}/{n}")
        for run in r["pwc"]["runs"][:1]:
            if run.get("hallucinated_in_plan"):
                print(f"   ⚠ pwc-план содержит выдуманные инструменты: "
                      f"{run['hallucinated_in_plan']}")
        print()

    # Итоговая таблица
    print("=" * 72)
    print("ИТОГО (доля успешных прогонов):")
    print(f"{'id':<5}{'single':<10}{'pwc':<10}{'pwc+val':<10}query")
    for r in results:
        print(f"{r['id']:<5}"
              f"{r['single']['pass']}/{n:<8}"
              f"{r['pwc']['pass']}/{n:<8}"
              f"{r['pwc_val']['pass']}/{n:<8}"
              f"{r['query'][:50]}")

    out = Path(__file__).parent / "eval_pwc_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    print(f"\nРезультаты: {out}")


if __name__ == "__main__":
    main()
