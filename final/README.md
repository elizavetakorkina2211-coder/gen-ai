# Silicon Sampling на данных GSS

Финальный проект курса «Практическое применение генеративного ИИ».
**Трек A** - LLM как дешёвый испытуемый: обуславливаем модель на реальные
демографические профили GSS, прогоняем анкету об экономических установках и
сравниваем синтетические ответы с реальными ответами тех же людей.

## Структура

```
final/
├── README.md          ← этот файл
├── requirements.txt
├── .env.example       ← шаблон для токена (без секрета)
├── config.py          ← переменные GSS, шкалы вопросов, пути
├── schemas.py         ← Pydantic-схемы + валидатор шкалы (бизнес-инвариант)
├── data_prep.py       ← GSS.dta → personas.jsonl + ground_truth.jsonl
├── rag.py             ← TF-IDF RAG по codebook.md (формулировки вопросов)
├── agents.py          ← 3 роли: интервьюер, персона, судья
├── pipeline.py        ← главный конвейер
├── eval.py            ← метрики: правильность + путь
├── llm_client.py      ← OpenAI-совместимый клиент + JSON-инструктор
├── mock_client.py     ← заглушка LLM (прогон без токена)
├── codebook.md        ← формулировки и шкалы 4 вопросов GSS
├── input/             ← GSS.dta, personas.jsonl, ground_truth.jsonl
└── output/            ← answers.jsonl, trace.jsonl, eval_table.csv, results.json
```

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env   # впиши свой токен в .env
```

## Запуск 

```bash
python data_prep.py && python pipeline.py --limit 15 && python eval.py
```

Или по шагам:

```bash
python data_prep.py            # подготовить персоны из GSS.dta
python pipeline.py --mock      # прогон БЕЗ токена (заглушка, для проверки)
python pipeline.py --limit 15  # реальный прогон, 15 персон
python eval.py                 # метрики → output/
```

## Техники курса

RAG (`rag.py`), синтетические персоны (`agents.respond`), мультиагент
(интервьюер + персона + судья), LLM-as-judge (`agents.judge`), структурированный
вывод с валидатором шкалы (`schemas.py`).
