"""
Раунд 6 — Кэширование промптов
================================
Каждый раунд 1, 2, 3 шлёт на сервер один и тот же transcript.txt.
Это входные токены, за которые мы платим каждый раз. Если транскрипт
большой (50k токенов) и мы делаем 10 операций — это 500k токенов на
повторении. Деньги в трубу.

Решение — кэширование промптов: провайдер запоминает префикс системного
промпта (или его части) и при следующем запросе с тем же префиксом
считает его как «попадание в кэш» — дешевле в 5-10 раз. У DeepSeek это
работает автоматически: достаточно держать transcript в начале промпта
без изменений между запросами.

Задача:
  1. Прогнать extract_aspects ДВАЖДЫ подряд на том же transcript.
     Замерить токены через response.usage (нужен with_completion=True).
  2. У DeepSeek в usage есть prompt_cache_hit_tokens и
     prompt_cache_miss_tokens. Посчитать процент попадания в кэш.
  3. Прогнать в третий раз, но с ИЗМЕНЕННЫМ системным промптом
     (добавить случайную строку). Доля попаданий упадёт.
  4. Прогнать в четвёртый раз, восстановив промпт. Доля попаданий вернётся.

  Вывод: кэш ОЧЕНЬ чувствителен к точному совпадению префикса.
  Любое изменение — кэш сбрасывается.

Запуск:
    python 10_prompt_caching.py
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from llm_client import get_model, make_client
from prompts import ASPECTS_SYSTEM
from schema import ParticipantSentiment

client = make_client()
MODEL = get_model()


def run_once(system_prompt: str, transcript: str) -> dict:
    """Один extract_aspects-вызов, вернуть {time, usage}.

    Подсказка: make_client().chat.completions.create поддерживает
    with_completion=True — вернёт кортеж (Persona, completion). Из
    completion.usage возьми prompt_tokens, completion_tokens, а также
    completion.usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens
    (специфика DeepSeek).
    """
    # TODO
    raise NotImplementedError


def show(label: str, info: dict) -> None:
    total_in = info["prompt_tokens"]
    cache_hit = info.get("cache_hit", 0)
    cache_miss = info.get("cache_miss", total_in)
    pct = cache_hit / total_in * 100 if total_in else 0
    print(
        f"  {label:<32} время={info['time']:>5.1f}с  "
        f"вход={total_in:>5}  попаданий={cache_hit:>5} ({pct:>3.0f}%)  промахов={cache_miss:>5}"
    )


def main() -> None:
    transcript = Path("transcript.txt").read_text(encoding="utf-8")
    print(f"Модель: {MODEL}, транскрипт: {len(transcript)} символов\n")

    print("━━━ Прогон 1 (холодный) ━━━")
    a = run_once(ASPECTS_SYSTEM, transcript)
    show("первый раз, промпт A", a)

    print("\n━━━ Прогон 2 (тот же промпт) ━━━")
    b = run_once(ASPECTS_SYSTEM, transcript)
    show("повтор, промпт A", b)

    print("\n━━━ Прогон 3 (промпт чуть отличается — кэш должен слететь) ━━━")
    modified = ASPECTS_SYSTEM + f"\n# случайный комментарий: {uuid.uuid4()}\n"
    c = run_once(modified, transcript)
    show("модифицированный промпт", c)

    print("\n━━━ Прогон 4 (возвращаем оригинальный промпт) ━━━")
    d = run_once(ASPECTS_SYSTEM, transcript)
    show("снова промпт A", d)

    print("\nЧто увидеть:")
    print("  • Прогон 2 vs 1: попаданий ≫ 0, промахов мало → кэш работает.")
    print("  • Прогон 3: попаданий резко меньше — изменение префикса сбрасывает кэш.")
    print(
        "  • Прогон 4: попаданий опять много — кэш не «забыл», просто промпт был другой."
    )


if __name__ == "__main__":
    main()
