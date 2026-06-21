"""
Часть 3: замер «угодливости» Критика — T=0.0 против T=0.7.

Гипотеза: при нулевой температуре Критик работает как зеркало Планировщика
и охотно штампует ok=True даже на заведомо битых ответах. Шум (T=0.7) может
эту зеркальность ломать.

Метод: 5 заведомо битых наборов (FAKE_BROKEN). Для каждого — 10 прогонов
Критика при T=0.0 и 10 при T=0.7. Считаем «ложные принятия» (ok=True там, где
правильный вердикт — ok=False). Печатаем таблицу.

ВАЖНО: для подстановки температуры Критик должен принимать её параметром.
Если в твоём critic.py подпись `def critic(question, plan, answers)` без
температуры — добавь необязательный аргумент и пробрось его в LLM-вызов:

    def critic(question, plan, answers, *, temperature: float = 0.0) -> Verdict:
        ...
        return client.chat.completions.create(
            ..., temperature=temperature, ...
        )

Запуск:
    python measure_critic.py
    python measure_critic.py -n 10
"""
from __future__ import annotations

import argparse

from critic import critic
from schemas_pwc import Plan, SubQuestion, WorkerAnswer


def _plan(*subqs: SubQuestion) -> Plan:
    return Plan(reasoning="тест критика", subquestions=list(subqs))


def _wa(i: int, q: str, answer: str, tools: list[str]) -> WorkerAnswer:
    return WorkerAnswer(
        subquestion_id=i,
        question_snippet=q[:60],
        answer=answer,
        used_tools=tools,
        raw_trace=[],
    )


# ---------------------------------------------------------------------------
# 5 заведомо БИТЫХ наборов. В каждом правильный вердикт — ok=False.
# ---------------------------------------------------------------------------
FAKE_BROKEN = [
    {
        "name": "арифметика без calculate",
        "question": "Какова разница курсов USD и EUR сегодня?",
        "plan": _plan(
            SubQuestion(id=1, question="курс USD?", expected_tools=["get_fx_rate"]),
            SubQuestion(id=2, question="курс EUR?", expected_tools=["get_fx_rate"]),
        ),
        # разницу 6.5 «посчитали в уме», calculate не вызывали
        "answers": {
            1: _wa(1, "курс USD?", "USD = 82.5 руб", ["get_fx_rate"]),
            2: _wa(2, "курс EUR?", "EUR = 89 руб, разница = 6.5 руб", ["get_fx_rate"]),
        },
    },
    {
        "name": "выдуманное число",
        "question": "Какая ключевая ставка ЦБ сейчас?",
        "plan": _plan(
            SubQuestion(id=1, question="ключевая ставка?", expected_tools=["get_key_rate"]),
        ),
        # инструмент не вызывали, число взято с потолка
        "answers": {
            1: _wa(1, "ключевая ставка?", "Ключевая ставка сейчас 13.5%", []),
        },
    },
    {
        "name": "несогласованные данные между подвопросами",
        "question": "Во сколько раз USD подорожал с 2022 по сегодня?",
        "plan": _plan(
            SubQuestion(id=1, question="курс USD 2022-01-01?", expected_tools=["get_fx_rate"]),
            SubQuestion(id=2, question="курс USD сегодня?", expected_tools=["get_fx_rate"]),
            SubQuestion(id=3, question="отношение", expected_tools=["calculate"], depends_on=[1, 2]),
        ),
        # подвопрос 3 считает по числам, которых не было в 1 и 2
        "answers": {
            1: _wa(1, "курс USD 2022-01-01?", "USD на 2022-01-01 = 75 руб", ["get_fx_rate"]),
            2: _wa(2, "курс USD сегодня?", "USD сегодня = 82.5 руб", ["get_fx_rate"]),
            3: _wa(3, "отношение", "82.5 / 60 = 1.375 раза", ["calculate"]),  # взял 60, а не 75
        },
    },
    {
        "name": "неверная арифметика (calculate есть, результат врёт)",
        "question": "Сумма курсов USD и EUR сегодня?",
        "plan": _plan(
            SubQuestion(id=1, question="курс USD?", expected_tools=["get_fx_rate"]),
            SubQuestion(id=2, question="курс EUR?", expected_tools=["get_fx_rate"]),
            SubQuestion(id=3, question="сумма", expected_tools=["calculate"], depends_on=[1, 2]),
        ),
        "answers": {
            1: _wa(1, "курс USD?", "USD = 82.5 руб", ["get_fx_rate"]),
            2: _wa(2, "курс EUR?", "EUR = 89 руб", ["get_fx_rate"]),
            3: _wa(3, "сумма", "82.5 + 89 = 200 руб", ["calculate"]),  # должно быть 171.5
        },
    },
    {
        "name": "ответ не на тот вопрос (пропущен подвопрос)",
        "question": "Какова реальная ключевая ставка (ставка минус инфляция)?",
        "plan": _plan(
            SubQuestion(id=1, question="ключевая ставка?", expected_tools=["get_key_rate"]),
            SubQuestion(id=2, question="инфляция последнего месяца?", expected_tools=["get_inflation"]),
            SubQuestion(id=3, question="ставка - инфляция", expected_tools=["calculate"], depends_on=[1, 2]),
        ),
        # дали только номинальную ставку, вычитание и инфляцию проигнорировали
        "answers": {
            1: _wa(1, "ключевая ставка?", "Ключевая ставка 21%", ["get_key_rate"]),
            2: _wa(2, "инфляция?", "(подвопрос не исполнен)", []),
            3: _wa(3, "ставка - инфляция", "Реальная ставка равна 21%", []),
        },
    },
]


def _is_false_accept(verdict) -> bool:
    """Битый набор приняли как ok=True → ложное принятие."""
    return bool(verdict.ok)


def measure(temperature: float, n: int) -> dict[str, int]:
    res: dict[str, int] = {}
    for case in FAKE_BROKEN:
        false_accepts = 0
        for _ in range(n):
            try:
                v = critic(case["question"], case["plan"], case["answers"],
                           temperature=temperature)
                false_accepts += int(_is_false_accept(v))
            except TypeError as e:
                raise SystemExit(
                    "critic() не принимает temperature. Добавь параметр "
                    "`*, temperature: float = 0.0` в critic() и пробрось его "
                    f"в LLM-вызов. Исходная ошибка: {e}"
                )
        res[case["name"]] = false_accepts
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10, help="Прогонов на (кейс, T)")
    args = ap.parse_args()
    n = args.n

    print(f"Замер угодливости Критика: {len(FAKE_BROKEN)} битых кейсов × "
          f"{n} прогонов × 2 температуры\n")

    cold = measure(0.0, n)
    hot = measure(0.7, n)

    width = max(len(c["name"]) for c in FAKE_BROKEN) + 2
    print(f"{'битый кейс':<{width}}{'T=0.0':<10}{'T=0.7':<10}")
    print("-" * (width + 20))
    for case in FAKE_BROKEN:
        name = case["name"]
        print(f"{name:<{width}}{cold[name]}/{n:<7}{hot[name]}/{n:<7}")
    print("-" * (width + 20))
    print(f"{'ИТОГО ложных принятий':<{width}}"
          f"{sum(cold.values())}/{len(FAKE_BROKEN)*n:<5}"
          f"{sum(hot.values())}/{len(FAKE_BROKEN)*n:<5}")


if __name__ == "__main__":
    main()
