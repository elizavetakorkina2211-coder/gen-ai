"""
Раунд 3a — Стратегии разбиения
==============================
Map-Reduce начинается с разбиения. У нашего транскрипта 4 говорящих и
~150 строк — для одного запроса разбиение вообще не нужно. Но как только
он вырастет до 200k токенов — придётся резать. И тут возникает вопрос:
КАК резать?

Задача:
  Реализовать ТРИ функции разбиения. На нашем коротком transcript.txt
  посчитать: сколько фрагментов, средний размер, минимум/максимум.
  Это даст почувствовать разницу подходов «руками».

Запуск:
    python 6_split_chunking.py
"""

from __future__ import annotations

import re
from pathlib import Path

SPEAKER_RE = re.compile(r"^([А-ЯЁA-Z][а-яёa-zА-ЯЁA-Z]+):\s", re.MULTILINE)
_SKIP_SPEAKERS = {"Модератор", "Moderator", "Дата", "Участники", "Date"}


def split_by_speaker(transcript: str) -> list[str]:
    """Разбить по говорящему. Шапку (поля Дата/Участники/...) выкинуть.

    Подсказка: текст до первого "═══" — это метаданные, режь их.
    """
    # TODO
    raise NotImplementedError


def split_by_chars(transcript: str, max_chars: int = 1500) -> list[str]:
    """Разбить на куски по N символов, стараясь резать по \\n\\n."""
    # TODO: накопительно собирать абзацы, пока не упрётся в max_chars.
    raise NotImplementedError


def split_sliding(transcript: str, window: int = 1500, overlap: int = 300) -> list[str]:
    """Скользящее окно: каждый следующий кусок начинается на (window-overlap)
    символов позже. Полезно, когда смысловые единицы могут пересекать
    границы фиксированного разбиения.
    """
    # TODO
    raise NotImplementedError


def stats(chunks: list[str], label: str) -> None:
    if not chunks:
        print(f"  {label:<20} 0 фрагментов")
        return
    sizes = [len(c) for c in chunks]
    print(
        f"  {label:<20} n={len(chunks):<3} "
        f"средн.={sum(sizes) // len(sizes):>5} "
        f"мин={min(sizes):>5} макс={max(sizes):>5}"
    )


def main() -> None:
    transcript = Path("transcript.txt").read_text(encoding="utf-8")
    print(f"Транскрипт: {len(transcript)} символов\n")

    print("━━━ Три стратегии разбиения ━━━")
    stats(split_by_speaker(transcript), "по говорящим")
    stats(split_by_chars(transcript, max_chars=1500), "по размеру (1500)")
    stats(split_sliding(transcript, window=1500, overlap=300), "скользящее (1500,300)")

    print("\nЧто обсудить:")
    print(
        "  • для нашего короткого транскрипта разбиение по говорящим — очевидный выбор;"
    )
    print(
        "  • для 100-страничного отчёта разбиение по размеру даст однородные фрагменты;"
    )
    print("  • для длинного монолога эксперта скользящее окно не потеряет контекст.")


if __name__ == "__main__":
    main()
