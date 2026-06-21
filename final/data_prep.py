"""
Подготовка данных: из сырого GSS делаем профили (personas) и эталонные ответы
(ground_truth) для выбранных экономических вопросов.

Вход (любой из):
  input/GSS.dta            — реальный кумулятивный файл GSS (Stata), ИЛИ
  input/gss_fixture.csv    — маленький синтетический фикстур для отладки пайплайна
                             без скачивания GSS (НЕ выдавать за реальные данные!).

Выход:
  input/personas.jsonl     — демографические профили
  input/ground_truth.jsonl — реальные ответы тех же людей (бенчмарк)

Запуск:
  python data_prep.py            # авто: возьмёт GSS.dta, иначе фикстур
  python data_prep.py --make-fixture   # создать синтетический фикстур для теста
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from config import (
    DEMOGRAPHIC_VARS,
    INPUT_DIR,
    N_PERSONAS,
    RANDOM_SEED,
    SCALES,
    SURVEY_QUESTIONS,
)

# Человекочитаемые подписи кодов (минимальный набор; при чтении .dta берём
# value-labels из самого файла, эти словари — фолбэк/для фикстура).
LABELS = {
    "sex": {1: "мужчина", 2: "женщина"},
    "race": {1: "белый", 2: "чёрный", 3: "другая раса"},
    "degree": {0: "ниже среднего", 1: "среднее", 2: "колледж (2 года)",
               3: "бакалавр", 4: "магистр+"},
    "partyid": {0: "сильный демократ", 1: "демократ", 2: "склоняется к демократам",
                3: "независимый", 4: "склоняется к республиканцам",
                5: "республиканец", 6: "сильный республиканец"},
    "polviews": {1: "крайне либеральные", 2: "либеральные", 3: "умеренно либеральные",
                 4: "умеренные", 5: "умеренно консервативные", 6: "консервативные",
                 7: "крайне консервативные"},
    "region": {1: "Новая Англия", 2: "Средняя Атлантика", 3: "Восток Сев.-Центр",
               4: "Запад Сев.-Центр", 5: "Юж. Атлантика", 6: "Восток Юж.-Центр",
               7: "Запад Юж.-Центр", 8: "Горный", 9: "Тихоокеанский"},
}


def _income_bucket(realinc) -> str | None:
    if realinc is None or (isinstance(realinc, float) and np.isnan(realinc)):
        return None
    x = float(realinc)
    if x < 20000:
        return "низкий (<$20k)"
    if x < 50000:
        return "ниже среднего ($20–50k)"
    if x < 90000:
        return "средний ($50–90k)"
    return "высокий (>$90k)"


def load_raw() -> pd.DataFrame:
    dta = INPUT_DIR / "GSS.dta"
    fixture = INPUT_DIR / "gss_fixture.csv"
    if dta.exists():
        import pyreadstat
        df, _ = pyreadstat.read_dta(str(dta))
        df.columns = [c.lower() for c in df.columns]
        print(f"[data_prep] загружен реальный GSS: {df.shape[0]} строк")
        return df
    if fixture.exists():
        print("[data_prep] GSS.dta не найден — использую СИНТЕТИЧЕСКИЙ фикстур "
              "(не выдавать за реальные данные!)")
        return pd.read_csv(fixture)
    raise FileNotFoundError(
        "Нет ни input/GSS.dta, ни input/gss_fixture.csv. Скачай GSS "
        "(gssdataexplorer.norc.org → Quick Downloads → STATA) и положи как input/GSS.dta, "
        "либо создай фикстур: python data_prep.py --make-fixture"
    )


def build(df: pd.DataFrame) -> None:
    cols = DEMOGRAPHIC_VARS + SURVEY_QUESTIONS
    have = [c for c in cols if c in df.columns]
    sub = df[have].copy()
    # приводим к числам, выкидываем строки с пропусками в нужных полях
    for c in have:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    # ответы на анкету должны быть валидны по шкале
    for q in SURVEY_QUESTIONS:
        if q in sub.columns:
            sub = sub[sub[q].isin(SCALES[q])]
    sub = sub.dropna(subset=[c for c in DEMOGRAPHIC_VARS if c in sub.columns])
    print(f"[data_prep] после очистки осталось {len(sub)} полных респондентов")

    # стратифицированная выборка по polviews (чтобы покрыть весь спектр взглядов)
    n = min(N_PERSONAS, len(sub))
    if "polviews" in sub.columns and sub["polviews"].nunique() > 1:
        sample = (
            sub.groupby("polviews", group_keys=False)
            .apply(lambda g: g.sample(max(1, round(n * len(g) / len(sub))),
                                      random_state=RANDOM_SEED))
        )
        sample = sample.sample(min(n, len(sample)), random_state=RANDOM_SEED)
    else:
        sample = sub.sample(n, random_state=RANDOM_SEED)

    personas_path = INPUT_DIR / "personas.jsonl"
    truth_path = INPUT_DIR / "ground_truth.jsonl"
    with open(personas_path, "w", encoding="utf-8") as pf, \
         open(truth_path, "w", encoding="utf-8") as tf:
        for rid, (_, row) in enumerate(sample.iterrows()):
            persona = {
                "respondent_id": rid,
                "age": int(row["age"]) if "age" in row and not pd.isna(row["age"]) else None,
                "sex": LABELS["sex"].get(int(row.get("sex", 0)), None),
                "race": LABELS["race"].get(int(row.get("race", 0)), None),
                "degree": LABELS["degree"].get(int(row.get("degree", -1)), None),
                "income": _income_bucket(row.get("realinc")),
                "partyid": LABELS["partyid"].get(int(row.get("partyid", -1)), None),
                "polviews": LABELS["polviews"].get(int(row.get("polviews", -1)), None),
                "region": LABELS["region"].get(int(row.get("region", -1)), None),
            }
            truth = {"respondent_id": rid,
                     "answers": {q: int(row[q]) for q in SURVEY_QUESTIONS if q in row}}
            pf.write(json.dumps(persona, ensure_ascii=False) + "\n")
            tf.write(json.dumps(truth, ensure_ascii=False) + "\n")
    print(f"[data_prep] записано {len(sample)} профилей → {personas_path.name}, {truth_path.name}")


def make_fixture(n: int = 40) -> None:
    """Синтетический фикстур, чтобы прогнать пайплайн без скачивания GSS."""
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for _ in range(n):
        pol = rng.integers(1, 8)
        # ответы слегка коррелируют с polviews (для реалистичности отладки)
        lean = (pol - 4) / 3  # -1..1
        rows.append({
            "age": int(rng.integers(18, 85)),
            "sex": int(rng.integers(1, 3)),
            "race": int(rng.choice([1, 1, 1, 2, 3])),
            "degree": int(rng.integers(0, 5)),
            "realinc": float(rng.choice([12000, 35000, 70000, 120000])),
            "partyid": int(np.clip(round(3 + lean * 3 + rng.normal(0, 1)), 0, 6)),
            "polviews": int(pol),
            "region": int(rng.integers(1, 10)),
            "eqwlth": int(np.clip(round(4 + lean * 2 + rng.normal(0, 1)), 1, 7)),
            "helppoor": int(np.clip(round(3 + lean * 1.5 + rng.normal(0, 1)), 1, 5)),
            "helpnot": int(np.clip(round(3 + lean * 1.5 + rng.normal(0, 1)), 1, 5)),
            "getahead": int(rng.integers(1, 4)),
        })
    pd.DataFrame(rows).to_csv(INPUT_DIR / "gss_fixture.csv", index=False)
    print(f"[data_prep] создан фикстур input/gss_fixture.csv на {n} строк")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-fixture", action="store_true")
    a = ap.parse_args()
    if a.make_fixture:
        make_fixture()
        return
    build(load_raw())


if __name__ == "__main__":
    main()
