"""
Оркестратор: главный цикл Планировщик-Исполнитель-Критик.

Домашка С6:
- часть 1: validate_plan() + встройка в run_pwc (валидатор схемы);
- часть 2: _topological_levels() + execute_level() (параллельность);
- плюс закрыты семинарские TODO: replan/rework-ветки и _synthesize.

Флаги run_pwc:
- use_validator: включить валидатор схемы (для eval-конфигурации «pwc без валидатора»);
- parallel:      исполнять уровни параллельно (для замера ускорения).
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from critic import critic
from llm_client import get_model, make_raw_client
from planner import planner
from schemas_pwc import Plan, SubQuestion, WorkerAnswer
from worker import worker


# ===========================================================================
# Часть 1. Валидатор схемы между Планировщиком и Исполнителем
# ===========================================================================

VALID_TOOLS = {"get_fx_rate", "get_key_rate", "get_inflation", "calculate"}


def validate_plan(plan: Plan) -> list[str]:
    """Вернуть список ошибок плана (пустой список — всё ок).

    Проверяем:
      1. выдуманные инструменты в expected_tools (главная цель — class C/D
         галлюцинации вида get_cumulative_inflation, get_cagr, ...);
      2. пустой expected_tools у подвопроса;
      3. дублирующиеся id подвопросов;
      4. depends_on, ссылающийся на несуществующий id.

    Пустой план (subquestions=[]) ошибкой НЕ считается — это легальный ответ
    «задача нерешаема имеющимися инструментами».
    """
    errors: list[str] = []
    known_ids = {sq.id for sq in plan.subquestions}
    seen_ids: set[int] = set()

    for sq in plan.subquestions:
        bad_tools = sorted(set(sq.expected_tools) - VALID_TOOLS)
        if bad_tools:
            errors.append(
                f"подвопрос {sq.id}: несуществующие инструменты {bad_tools}; "
                f"разрешены только {sorted(VALID_TOOLS)}"
            )
        if not sq.expected_tools:
            errors.append(f"подвопрос {sq.id}: пустой список expected_tools")
        if sq.id in seen_ids:
            errors.append(f"дублирующийся id подвопроса: {sq.id}")
        seen_ids.add(sq.id)
        for dep in sq.depends_on:
            if dep not in known_ids:
                errors.append(
                    f"подвопрос {sq.id}: depends_on ссылается на несуществующий id {dep}"
                )
    return errors


def _make_validated_plan(
    question: str,
    *,
    feedback: str | None,
    use_validator: bool,
    max_fix: int,
    trace: list[dict[str, Any]],
    verbose: bool,
) -> Plan:
    """planner() + (опционально) цикл валидации: если в плане выдуманные
    инструменты — перепланируем с обратной связью, до max_fix попыток."""
    plan = planner(question, feedback=feedback)
    if not use_validator:
        return plan

    for attempt in range(max_fix):
        errors = validate_plan(plan)
        if not errors:
            return plan
        trace.append(
            {"iter": 0, "kind": "validator", "attempt": attempt, "errors": errors}
        )
        if verbose:
            print(f"  [validator ❌] {errors} → перепланировка")
        plan = planner(question, feedback=f"Инструменты не существуют: {errors}")
    return plan  # после max_fix попыток вернём как есть (eval это поймает)


# ===========================================================================
# Часть 2. Топологические уровни + параллельное исполнение
# ===========================================================================

def _topological_sort(subqs: list[SubQuestion]) -> list[SubQuestion]:
    """Плоский топологический порядок (depends_on раньше зависящих).

    Используется в последовательном режиме (parallel=False) и для замера
    «как было до распараллеливания»."""
    by_id = {s.id: s for s in subqs}
    ordered: list[SubQuestion] = []
    visited: set[int] = set()

    def visit(node_id: int, path: list[int]):
        if node_id in visited:
            return
        if node_id in path:
            raise ValueError(f"Цикл в depends_on: {path + [node_id]}")
        if node_id not in by_id:
            return
        for dep in by_id[node_id].depends_on:
            visit(dep, path + [node_id])
        visited.add(node_id)
        ordered.append(by_id[node_id])

    for sq in subqs:
        visit(sq.id, [])
    return ordered


def _topological_levels(subqs: list[SubQuestion]) -> list[list[SubQuestion]]:
    """Разбить подвопросы на уровни зависимостей.

    Внутри одного уровня зависимостей между подвопросами нет → их можно
    исполнять параллельно. Между уровнями зависимость есть → уровни строго
    по очереди. Алгоритм Кана «по слоям»: на каждом шаге берём все узлы, чьи
    зависимости уже разрешены. Ссылки на несуществующие id игнорируем (как и
    _topological_sort). Если готовых узлов нет, а узлы остались — цикл.
    """
    by_id = {s.id: s for s in subqs}
    deps = {s.id: {d for d in s.depends_on if d in by_id} for s in subqs}

    resolved: set[int] = set()
    remaining: set[int] = set(by_id)
    levels: list[list[SubQuestion]] = []

    while remaining:
        ready = [sid for sid in remaining if deps[sid] <= resolved]
        if not ready:
            raise ValueError(f"Цикл в depends_on среди {sorted(remaining)}")
        levels.append([by_id[sid] for sid in sorted(ready)])
        resolved |= set(ready)
        remaining -= set(ready)
    return levels


def execute_level(
    level: list[SubQuestion],
    prev_answers: dict[int, WorkerAnswer],
) -> dict[int, WorkerAnswer]:
    """Прогнать все подвопросы одного уровня параллельно.

    Внутри уровня зависимостей нет, поэтому каждый worker видит одни и те же
    prev_answers (ответы предыдущих уровней) и не ждёт соседей. Один worker —
    без накладных расходов на пул потоков.
    """
    if not level:
        return {}
    if len(level) == 1:
        sq = level[0]
        return {sq.id: worker(sq, prev_answers=prev_answers)}

    results: dict[int, WorkerAnswer] = {}
    with ThreadPoolExecutor(max_workers=len(level)) as ex:
        future_to_id = {ex.submit(worker, sq, prev_answers): sq.id for sq in level}
        for fut, sq_id in future_to_id.items():
            results[sq_id] = fut.result()
    return results


# ===========================================================================
# Синтез финального ответа
# ===========================================================================

_SYNTH_SYSTEM = """\
Ты собираешь финальный ответ пользователю из ответов на подвопросы.
Дай 1-2 фразы: прямой ответ на исходный вопрос, обязательно с числом и
единицей измерения. Не добавляй рассуждений и названий инструментов.
Если в ответах есть пометка про fallback_csv — коротко оговорись, что число
взято из локального архива.
"""


def _synthesize(question: str, plan: Plan, answers: dict[int, WorkerAnswer]) -> str:
    """Собрать финальный ответ одним LLM-вызовом без tools."""
    if not answers:
        return plan.reasoning or "Ответ собрать не удалось: план пуст."

    bullets = "\n".join(f"  {i}. {answers[i].answer}" for i in sorted(answers))
    fallback = " · ".join(answers[i].answer for i in sorted(answers))
    user = (
        f"Исходный вопрос: {question}\n\n"
        f"Ответы на подвопросы:\n{bullets}\n\n"
        f"Собери финальный ответ."
    )
    try:
        client = make_raw_client()
        resp = client.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": _SYNTH_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or fallback
    except Exception:
        return fallback


# ===========================================================================
# Главный цикл
# ===========================================================================

def run_pwc(
    question: str,
    *,
    max_iter: int = 3,
    verbose: bool = True,
    use_validator: bool = True,
    parallel: bool = True,
    max_fix: int = 2,
) -> dict[str, Any]:
    """Запустить цикл Планировщик-Исполнитель-Критик.

    use_validator — включить валидатор схемы (часть 1);
    parallel      — исполнять независимые подвопросы параллельно (часть 2).
    """
    trace: list[dict[str, Any]] = []

    # --- Планирование + валидатор схемы ---
    plan = _make_validated_plan(
        question, feedback=None, use_validator=use_validator,
        max_fix=max_fix, trace=trace, verbose=verbose,
    )
    trace.append(
        {
            "iter": 0,
            "kind": "plan",
            "reasoning": plan.reasoning,
            "subquestions": [sq.model_dump() for sq in plan.subquestions],
        }
    )
    if verbose:
        print(f"\n[plan] {plan.reasoning}")
        for sq in plan.subquestions:
            print(f"  {sq.id}. [{','.join(sq.expected_tools)}] {sq.question}")

    answers: dict[int, WorkerAnswer] = {}

    for iter_num in range(1, max_iter + 1):
        answers = {}

        if parallel:
            for level in _topological_levels(plan.subquestions):
                level_answers = execute_level(level, answers)
                answers.update(level_answers)
                for sq in level:
                    ans = answers[sq.id]
                    trace.append(
                        {"iter": iter_num, "kind": "worker", "sq_id": sq.id,
                         "used_tools": ans.used_tools, "answer": ans.answer}
                    )
                    if verbose:
                        print(f"  [{sq.id}] → {ans.answer}   tools={ans.used_tools}")
        else:
            for sq in _topological_sort(plan.subquestions):
                ans = worker(sq, prev_answers=answers)
                answers[sq.id] = ans
                trace.append(
                    {"iter": iter_num, "kind": "worker", "sq_id": sq.id,
                     "used_tools": ans.used_tools, "answer": ans.answer}
                )
                if verbose:
                    print(f"  [{sq.id}] → {ans.answer}   tools={ans.used_tools}")

        verdict = critic(question, plan, answers)
        trace.append(
            {"iter": iter_num, "kind": "verdict", "ok": verdict.ok,
             "action": verdict.action, "reason": verdict.reason,
             "rework_ids": verdict.rework_ids}
        )
        if verbose:
            mark = "✅" if verdict.ok else "❌"
            print(f"  [critic {mark}] {verdict.action}: {verdict.reason}")

        if verdict.ok:
            final = _synthesize(question, plan, answers)
            return {
                "answer": final, "plan": plan, "answers": answers,
                "trace": trace, "iterations": iter_num,
            }

        # --- replan / rework ветки ---
        if verdict.action == "replan":
            plan = _make_validated_plan(
                question, feedback=verdict.reason, use_validator=use_validator,
                max_fix=max_fix, trace=trace, verbose=verbose,
            )
        elif verdict.action == "rework":
            fb = f"Переделать подвопросы {verdict.rework_ids}. Замечание: {verdict.reason}"
            plan = _make_validated_plan(
                question, feedback=fb, use_validator=use_validator,
                max_fix=max_fix, trace=trace, verbose=verbose,
            )
        else:  # action == "accept" но ok=False — не должно случаться; страхуемся
            break

    return {
        "answer": None,
        "error": f"не удалось получить вердикт 'accept' за {max_iter} итераций",
        "plan": plan,
        "answers": answers,
        "trace": trace,
        "iterations": max_iter,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+", help="Вопрос к агенту")
    ap.add_argument("--max-iter", type=int, default=3)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-validator", action="store_true",
                    help="Отключить валидатор схемы")
    ap.add_argument("--sequential", action="store_true",
                    help="Исполнять подвопросы последовательно (без параллели)")
    ap.add_argument("--trace", type=Path, default=None,
                    help="Куда сохранить JSON-лог (если задан)")
    args = ap.parse_args()

    q = " ".join(args.query)
    res = run_pwc(
        q, max_iter=args.max_iter, verbose=not args.quiet,
        use_validator=not args.no_validator, parallel=not args.sequential,
    )

    print("\n=== ВОПРОС ===")
    print(q)
    print("\n=== ОТВЕТ ===")
    print(res.get("answer") or res.get("error"))
    print(f"\n(итераций: {res.get('iterations', '?')})")

    if args.trace:
        args.trace.write_text(
            json.dumps({"query": q, **_serialize(res)}, ensure_ascii=False,
                       indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Трейс сохранён: {args.trace}")


def _serialize(res: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in res.items():
        if k == "plan" and v is not None:
            out[k] = v.model_dump()
        elif k == "answers":
            out[k] = {i: a.model_dump() for i, a in v.items()}
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    main()
