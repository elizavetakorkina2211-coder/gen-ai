"""
Юнит-тест валидатора схемы (часть 1).

Зачем: на DeepSeek-v4 Планировщик дисциплинирован и сам не выдумывает
инструменты, поэтому в eval валидатор почти не срабатывает «вживую». Но
требование задания — чтобы валидатор ЛОВИЛ минимум 2 типа выдуманных
инструментов. Доказываем это детерминированно, на синтетических планах,
без обращения к LLM.

Запуск:
    python test_validator.py
"""
from __future__ import annotations

from orchestrator import validate_plan
from schemas_pwc import Plan, SubQuestion


def _plan(*subqs: SubQuestion) -> Plan:
    return Plan(reasoning="тест валидатора", subquestions=list(subqs))


def _sq(i: int, tools: list[str], deps: list[int] | None = None) -> SubQuestion:
    return SubQuestion(id=i, question=f"q{i}", expected_tools=tools, depends_on=deps or [])


def main() -> None:
    # 1. выдуманный get_cumulative_inflation (класс ошибки D из Q3)
    e = validate_plan(_plan(_sq(1, ["get_cumulative_inflation"]), _sq(2, ["get_fx_rate"])))
    assert any("get_cumulative_inflation" in x for x in e), e
    print("✓ ловит выдуманный get_cumulative_inflation")

    # 2. выдуманный get_cagr (2-й тип — то, что пытались спровоцировать в Q4)
    e = validate_plan(_plan(_sq(1, ["get_cagr", "get_fx_rate"])))
    assert any("get_cagr" in x for x in e), e
    print("✓ ловит выдуманный get_cagr (2-й тип)")

    # 3. выдуманный get_gdp (3-й тип — домен без данных)
    e = validate_plan(_plan(_sq(1, ["get_gdp"])))
    assert any("get_gdp" in x for x in e), e
    print("✓ ловит выдуманный get_gdp (3-й тип)")

    # 4. корректный план — ошибок нет
    p = _plan(_sq(1, ["get_fx_rate"]), _sq(2, ["get_fx_rate"]), _sq(3, ["calculate"], [1, 2]))
    assert validate_plan(p) == [], validate_plan(p)
    print("✓ корректный план проходит без ошибок")

    # 5. пустой план (нерешаемая задача) — НЕ ошибка
    assert validate_plan(_plan()) == []
    print("✓ пустой план не считается ошибкой")

    # 6. дополнительно: пустой expected_tools и битый depends_on
    e = validate_plan(_plan(_sq(1, [], [99])))
    assert any("пустой" in x for x in e) and any("99" in x for x in e), e
    print("✓ ловит пустой expected_tools и depends_on на несуществующий id")

    print("\nВалидатор ловит 3 типа выдуманных инструментов "
          "(требование задания — минимум 2). Все тесты прошли.")


if __name__ == "__main__":
    main()
