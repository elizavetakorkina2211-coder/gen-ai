"""
Главный конвейер silicon sampling.

Для каждой персоны × вопрос:
  1) RAG: достаём формулировку и шкалу вопроса из codebook.md.
  2) Мультиагент: интервьюер проверяет вопрос на двусмысленность.
  3) Персона отвечает (структурированный вывод + валидатор шкалы).
  4) LLM-as-judge оценивает связность и галлюцинации.

Ошибки валидации (ответ вне шкалы и т.п.) НЕ роняют прогон — считаем их как
пойманные галлюцинации шкалы.

Запуск:
  python pipeline.py            # реальный DeepSeek (нужен .env)
  python pipeline.py --mock     # без сети, на заглушке — проверить плумбинг
  python pipeline.py --limit 5  # только первые 5 персон
"""
from __future__ import annotations

import argparse
import datetime
import json
import uuid

from pydantic import ValidationError

import agents
from config import OUTPUT_DIR, INPUT_DIR, SURVEY_QUESTIONS
from rag import CodebookRAG
from schemas import Persona


def _load_personas(limit: int | None) -> list[Persona]:
    path = INPUT_DIR / "personas.jsonl"
    if not path.exists():
        raise FileNotFoundError("Нет input/personas.jsonl — сначала запусти data_prep.py")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        out.append(Persona(**json.loads(line)))
    return out[:limit] if limit else out


def run(mock: bool = False, limit: int | None = None) -> None:
    if mock:
        from mock_client import make_mock_client
        client, model = make_mock_client(), "mock"
    else:
        from llm_client import make_client, get_model
        client, model = make_client(), get_model()

    rag = CodebookRAG()
    personas = _load_personas(limit)
    run_id = uuid.uuid4().hex

    answers_path = OUTPUT_DIR / "answers.jsonl"
    trace_path = OUTPUT_DIR / "trace.jsonl"
    af = open(answers_path, "w", encoding="utf-8")
    tf = open(trace_path, "a", encoding="utf-8")  # режим 'a' — лог копится

    def log(rec: dict):
        line = {"run_id": run_id,
                "ts": datetime.datetime.now().isoformat(timespec="seconds")}
        line.update(rec)
        tf.write(json.dumps(line, ensure_ascii=False) + "\n")

    n_scale_errors = 0
    for p in personas:
        for qid in SURVEY_QUESTIONS:
            doc = rag.by_id(qid)            # шаг 1 — RAG
            step = 1
            # шаг 2 — интервьюер (мультиагент)
            flag = agents.interview(client, model, p, qid, doc)
            log({"rid": p.respondent_id, "qid": qid, "step": step,
                 "agent": "interviewer", "ambiguous": flag.ambiguous,
                 "reason": flag.reason})
            step += 1
            # шаг 3 — персона отвечает (+ ловим ошибку шкалы как галлюцинацию)
            rec = {"respondent_id": p.respondent_id, "question_id": qid}
            try:
                ans = agents.respond(client, model, p, qid, doc)
                rec.update({"answer_value": ans.answer_value,
                            "rationale": ans.rationale,
                            "confidence": ans.confidence,
                            "scale_error": False})
                log({"rid": p.respondent_id, "qid": qid, "step": step,
                     "agent": "respondent", "answer": ans.answer_value,
                     "confidence": ans.confidence})
                step += 1
                # шаг 4 — судья
                verdict = agents.judge(client, model, p, doc, ans)
                rec.update({"coherent": verdict.coherent,
                            "hallucinated_reasoning": verdict.hallucinated_reasoning,
                            "judge_issue": verdict.issue})
                log({"rid": p.respondent_id, "qid": qid, "step": step,
                     "agent": "judge", "coherent": verdict.coherent,
                     "hallucinated": verdict.hallucinated_reasoning})
            except ValidationError as e:
                n_scale_errors += 1
                rec.update({"answer_value": None, "scale_error": True,
                            "error": str(e)[:200]})
                log({"rid": p.respondent_id, "qid": qid, "step": step,
                     "agent": "respondent", "scale_error": True})
            rec.update({"ambiguous": flag.ambiguous})
            af.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[pipeline] персона {p.respondent_id} готова")

    af.close()
    tf.close()
    print(f"\n[pipeline] записано → {answers_path.name}, {trace_path.name}")
    print(f"[pipeline] пойманных ошибок шкалы (галлюцинаций): {n_scale_errors}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="без сети, на заглушке")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(mock=a.mock, limit=a.limit)


if __name__ == "__main__":
    main()
