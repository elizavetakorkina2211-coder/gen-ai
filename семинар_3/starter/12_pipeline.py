"""
Финал — Сборка конвейера
==========================
Всё, что мы разложили по раундам 1-7, теперь собираем в один analyze().
Никаких новых концепций — только связывание. На входе путь к транскрипту,
на выходе папка output/ со всеми артефактами.

Задача:
  Дописать analyze(transcript_path, out_dir). Запустить, проверить,
  что в out_dir/ появилось:
    • participants.json + participants.csv
    • aspects.json + heatmap.png
    • summary.json
    • judge_report.json
    • metrics.json (полнота/точность/достоверность)

Запуск:
    python 12_pipeline.py transcript.txt
    python 12_pipeline.py transcripts/bank_olimp.txt output/olimp
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_p = importlib.import_module("2_extract_participants")
extract_participants = _p.extract_participants

_a = importlib.import_module("4_extract_aspects")
extract_aspects = _a.extract_aspects
check_quotes = _a.check_quotes
build_heatmap = _a.build_heatmap

_mr = importlib.import_module("7_map_reduce")
summarize_discussion = _mr.summarize_discussion

_j = importlib.import_module("9_judge")
judge = _j.judge

_eval = importlib.import_module("3_evaluate_ie")
fidelity = _eval.fidelity


def analyze(transcript_path: str, out_dir: str = "output") -> None:
    """Полный конвейер: транскрипт → набор артефактов в out_dir/."""
    # TODO:
    #   1. Создать папку out_dir, прочитать transcript.
    #   2. extract_participants → JSON + CSV
    #   3. extract_aspects + check_quotes → JSON + heatmap
    #   4. summarize_discussion → JSON
    #   5. judge → JSON (если есть эталон)
    #   6. метрики (достоверность, при наличии эталона — полнота/точность) → JSON
    #   7. вывести в консоль заголовок и ключевые цифры.
    raise NotImplementedError


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python 12_pipeline.py <transcript.txt> [out_dir]")
        sys.exit(1)
    transcript_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    analyze(transcript_path, out_dir)


if __name__ == "__main__":
    main()
