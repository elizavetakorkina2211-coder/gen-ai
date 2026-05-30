"""
Раунд 2 — Аспектный анализ + тепловая карта
=============================================
Теперь не просто «список жалоб», а структурированный взгляд: для каждого
участника — оценка по фиксированному набору аспектов (price/speed/ux/
support/security). На выходе — тепловая карта «участник × аспект».

Задача:
  1. В schema.py: AspectSentiment + ParticipantSentiment.
  2. В prompts.py: ASPECTS_SYSTEM (требование точной цитаты на русском,
     возврат только тех аспектов, что упомянуты).
  3. extract_aspects() — один вызов модели на весь транскрипт.
  4. build_heatmap() — тепловая карта (seaborn) участник × аспект.
  5. check_quotes() — на этом этапе ОБЯЗАТЕЛЬНО проверять цитаты:
     модель тут регулярно «сочиняет» (на DeepSeek типично 2-4 выдуманные
     цитаты).

Запуск:
    python 4_extract_aspects.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from llm_client import get_model, make_client
from prompts import ASPECTS_SYSTEM  # дополни prompts.py
from schema import ParticipantSentiment  # дополни schema.py

client = make_client()
MODEL = get_model()


def extract_aspects(transcript: str) -> list[ParticipantSentiment]:
    # TODO: один запрос, response_model=list[ParticipantSentiment], max_retries=3
    raise NotImplementedError


def check_quotes(
    aspects: list[ParticipantSentiment],
    transcript: str,
) -> list[tuple[str, str]]:
    """Вернуть пары (имя, ghost-цитата) — те, что НЕ найдены в исходном тексте.

    Не пытайся искать дословно: модель может слегка переформулировать.
    Бери первые 30 символов цитаты в lowercase и ищи подстроку.
    """
    # TODO
    raise NotImplementedError


def build_heatmap(
    aspects: list[ParticipantSentiment],
    out_path: str = "heatmap.png",
) -> None:
    """Матрица participant × aspect, sentiment → {+1, 0, -1}, NaN если не упомянут."""
    # TODO: построить numpy-матрицу + seaborn.heatmap (cmap="RdYlGn", center=0).
    raise NotImplementedError


def main() -> None:
    transcript = Path("transcript.txt").read_text(encoding="utf-8")

    aspects = extract_aspects(transcript)
    print(
        f"Найдено: {len(aspects)} участников, всего "
        f"{sum(len(p.aspects) for p in aspects)} оценок."
    )

    ghosts = check_quotes(aspects, transcript)
    if ghosts:
        print(f"\n⚠ {len(ghosts)} цитат не найдено в транскрипте:")
        for name, q in ghosts[:5]:
            print(f"  {name}: «{q[:80]}»")

    build_heatmap(aspects)
    print("\nСохранено: heatmap.png")

    # Сохраним в JSON для следующих раундов.
    out = [p.model_dump() for p in aspects]
    Path("aspects.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Сохранено: aspects.json")


if __name__ == "__main__":
    main()
