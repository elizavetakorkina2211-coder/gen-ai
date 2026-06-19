"""
Часть 2: замер ускорения от параллельного исполнения подвопросов.

Гоняем один и тот же вопрос в двух режимах (parallel=False / True), берём
медиану по нескольким прогонам (чтобы сгладить дрожание сети к ЦБ и LLM) и
печатаем ускорение. max_iter=1 — меряем ровно один проход без перепланировок.

Запуск:
    python bench_parallel.py
    python bench_parallel.py -n 5
"""
from __future__ import annotations

import argparse
import statistics
import time

from orchestrator import run_pwc

QUESTIONS = {
    "Q1 (2 независимых курса)":
        "Во сколько раз USD подорожал с 1 января 2022 по сегодня?",
    "Q5 (3 независимых курса)":
        "Каков суммарный курс корзины USD + EUR + CNY к рублю на сегодня?",
}


def _timeit(question: str, *, parallel: bool, n: int) -> float:
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        run_pwc(question, max_iter=1, verbose=False,
                use_validator=True, parallel=parallel)
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=3, help="Прогонов на режим (медиана)")
    args = ap.parse_args()

    print(f"Замер ускорения (медиана по {args.n} прогонам, max_iter=1)\n")
    print(f"{'вопрос':<28}{'послед., с':<14}{'паралл., с':<14}ускорение")
    for name, q in QUESTIONS.items():
        seq = _timeit(q, parallel=False, n=args.n)
        par = _timeit(q, parallel=True, n=args.n)
        speedup = seq / par if par else float("nan")
        print(f"{name:<28}{seq:<14.1f}{par:<14.1f}×{speedup:.2f}")


if __name__ == "__main__":
    main()
