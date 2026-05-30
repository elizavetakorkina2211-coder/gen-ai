"""
Раунд 7 — Многодокументный анализ
===================================
До сих пор у нас был один transcript. В реальности — 100 фокус-групп
за квартал, 5 разных банков, 3 региона. Вопросы меняются:

  • Какие темы появляются ПОВТОРНО у разных аудиторий?
  • Что специфично для банка X, чего нет у банка Y?
  • Как сгруппировать жалобы, чтобы не было «зоопарка тем»?

Задача:

  1. В transcripts/ уже лежат 5 готовых транскриптов разных банков.
  2. Прогнать extract_aspects + summarize_discussion параллельно на
     всех 5 транскриптах. Сохранить артефакты по каждому документу.
  3. Собрать ВСЕ жалобы со всех в одну таблицу: банк, имя, категория,
     тема, цитата.
  4. Топ-10 тем по частоте (по полю category).
  5. cross_bank_table: какие категории чаще встречаются у банка A,
     чем у банка B (сводная таблица).
  6. Свести 5 сводок в один MultiDocSummary через модель:
     «вот N коротких сводок разных банков; выдели общие паттерны и
     уникальные точки боли каждого».

Запуск:
    python 11_multi_doc.py
"""

from __future__ import annotations

import importlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from llm_client import get_model, make_client
from prompts import MULTI_DOC_SYSTEM
from schema import DiscussionSummary, MultiDocSummary

_aspects = importlib.import_module("4_extract_aspects")
extract_aspects = _aspects.extract_aspects
_mr = importlib.import_module("7_map_reduce")
summarize_discussion = _mr.summarize_discussion

client = make_client()
MODEL = get_model()


def list_transcripts(folder: str = "transcripts") -> list[Path]:
    paths = sorted(Path(folder).glob("*.txt"))
    if not paths:
        raise SystemExit(
            f"В {folder}/ нет .txt файлов. Должны лежать готовые "
            f"транскрипты; если их нет — сгенерируй generate_transcripts.py."
        )
    return paths


def process_one(path: Path) -> dict:
    """Один транскрипт → {bank, aspects, summary}."""
    transcript = path.read_text(encoding="utf-8")
    bank = path.stem  # имя файла без расширения = идентификатор банка
    # TODO: вызвать extract_aspects + summarize_discussion;
    #       вернуть словарь.
    raise NotImplementedError


def aggregate_aspects(docs: list[dict]) -> pd.DataFrame:
    """Собрать все оценки из всех транскриптов в одну широкую таблицу.

    Колонки: bank, name, aspect, sentiment, confidence, quote.
    """
    # TODO
    raise NotImplementedError


def top_topics(df: pd.DataFrame, n: int = 10) -> pd.Series:
    """Топ-N аспектов по частоте появления (counts)."""
    # TODO: df['aspect'].value_counts().head(n)
    raise NotImplementedError


def cross_bank_table(df: pd.DataFrame) -> pd.DataFrame:
    """Сводная таблица: строки — банки, столбцы — аспекты, значения — счётчик."""
    # TODO: pd.crosstab(df['bank'], df['aspect'])
    raise NotImplementedError


def consolidate(
    summaries: list[DiscussionSummary], banks: list[str]
) -> MultiDocSummary:
    """Свести N мини-сводок в общую. Вызов модели с response_model=MultiDocSummary.

    В промпте указать: «выдели общие паттерны (что встречается у всех)
    и уникальные точки боли каждого банка».
    """
    # TODO
    raise NotImplementedError


def main() -> None:
    paths = list_transcripts()
    print(f"Транскриптов: {len(paths)}")
    for p in paths:
        print(f"  • {p.name}")

    print("\n━━━ Параллельная обработка ━━━")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        docs = list(pool.map(process_one, paths))
    print(f"  готово за {time.time() - t0:.1f}с")

    df = aggregate_aspects(docs)
    print(f"\n━━━ Сводная таблица: {len(df)} строк ━━━")
    print(df.head())

    print(f"\n━━━ Топ-{10} тем по всем банкам ━━━")
    print(top_topics(df))

    print("\n━━━ Сводка по банкам ━━━")
    print(cross_bank_table(df))

    print("\n━━━ Многодокументная консолидация (через модель) ━━━")
    multi = consolidate(
        [d["summary"] for d in docs],
        [d["bank"] for d in docs],
    )
    print(f"\n  Общие паттерны:")
    for t in multi.common_themes:
        print(f"    • {t}")
    print(f"\n  Уникальные точки боли по банкам:")
    for bank, pains in multi.unique_per_bank.items():
        print(f"    [{bank}] {', '.join(pains)}")

    df.to_csv("multi_doc.csv", index=False, encoding="utf-8")
    Path("multi_doc_summary.json").write_text(
        multi.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print("\nСохранено: multi_doc.csv, multi_doc_summary.json")


if __name__ == "__main__":
    main()
