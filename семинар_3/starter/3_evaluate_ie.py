"""
Раунд 1.5 — Оценка качества извлечения
========================================
У нас есть два источника правды о транскрипте:
  • baseline_manual.json   — то, что выписали вручную в раунде 0 (эталон)
  • participants.json      — то, что нашла модель в раунде 1

Задача:
  Реализовать ТРИ метрики (имена функций оставлены латиницей, в выводе —
  русские названия):

  • полнота (coverage)      — какой процент тем из эталона нашла модель?
                полнота = |темы эталона ∩ темы модели| / |темы эталона|

  • точность (precision)    — какой процент жалоб модели реально есть в тексте?
                Проверять по подстроке `quote[:30].lower() in transcript.lower()`

  • достоверность (fidelity)— какой процент цитат, которые приводит модель,
                реально совпадает с текстом транскрипта (а не выдуман)?

  Для полноты сравнение тем — через модель (отдельный вызов «эта тема
  относится к одной из тем эталона?»). Это самая интересная часть —
  тут вы делаете модель-судью ещё до раунда 5.

Запуск:
    python 3_evaluate_ie.py
"""

from __future__ import annotations

import json
from pathlib import Path

from llm_client import get_model, make_client

client = make_client()
MODEL = get_model()


def load_artifacts() -> tuple[dict, list[dict], str]:
    baseline_path = Path("baseline_manual.json")
    if not baseline_path.exists():
        raise SystemExit("Сначала запусти раунд 0 — 1_baseline_manual.py.")
    participants_path = Path("participants.json")
    if not participants_path.exists():
        raise SystemExit("Сначала запусти раунд 1 — 2_extract_participants.py.")

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    participants = json.loads(participants_path.read_text(encoding="utf-8"))
    transcript = Path("transcript.txt").read_text(encoding="utf-8")
    return baseline, participants, transcript


def fidelity(participants: list[dict], transcript: str) -> float:
    """Доля цитат, реально найденных в транскрипте (подстрочный поиск)."""
    # TODO: пробежаться по всем concerns у всех participants;
    #       взять первые 30 символов quote, lowercase;
    #       проверить, есть ли в transcript.lower().
    raise NotImplementedError


def precision(participants: list[dict], transcript: str) -> float:
    """Точность: доля жалоб, реально подтверждённых текстом (≈ достоверность,
    но можно усложнить — например, проверять не только наличие цитаты,
    но и совпадение категории).

    Для базовой версии — можно считать точность == достоверности.
    Для продвинутой — добавь свой критерий.
    """
    # TODO
    raise NotImplementedError


def coverage(baseline: dict, participants: list[dict]) -> float:
    """Полнота: доля тем из эталона, которые модель нашла.

    Сравнение тем — отдельным вызовом модели. Для каждой темы из эталона
    спрашиваем: «есть ли среди этих {llm_topics} тема, эквивалентная
    «{baseline_topic}»?». Ответ — да/нет.
    """
    # TODO
    raise NotImplementedError


def main() -> None:
    baseline, participants, transcript = load_artifacts()

    f = fidelity(participants, transcript)
    p = precision(participants, transcript)
    c = coverage(baseline, participants)

    print("━━━ Метрики качества извлечения ━━━")
    print(f"  достоверность (fidelity)  = {f:.0%}   (цитаты совпадают с текстом)")
    print(f"  точность (precision)      = {p:.0%}   (жалобы подтверждены текстом)")
    print(f"  полнота (coverage)        = {c:.0%}   (темы эталона найдены моделью)")

    if c < 0.6:
        print("\n⚠ Низкая полнота — модель пропускает важные темы.")
        print("  Подкрути промпт IE_SYSTEM или увеличь temperature.")
    if f < 0.8:
        print("\n⚠ Низкая достоверность — модель «сочиняет» цитаты.")
        print("  Это галлюцинации. Усиль требование «дословно из текста» в промпте.")


if __name__ == "__main__":
    main()
