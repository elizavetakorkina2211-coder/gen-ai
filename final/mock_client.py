"""
Заглушка LLM-клиента: тот же интерфейс, что у llm_client.JsonClient
(`client.chat.completions.create(..., response_model=...)`), но без сети.

Нужна, чтобы прогнать весь пайплайн и eval без токена DeepSeek — проверить
плумбинг, схемы, метрики. Ответы детерминированы по хешу промпта.
"""
from __future__ import annotations

import hashlib
from typing import Type, TypeVar

from schemas import AmbiguityFlag, JudgeVerdict, SurveyAnswer

T = TypeVar("T")


def _seed(messages: list[dict]) -> int:
    blob = "".join(m.get("content", "") for m in messages)
    return int(hashlib.sha1(blob.encode()).hexdigest(), 16)


class _MockCompletions:
    def create(self, *, model, messages, response_model: Type[T], **kw) -> T:
        s = _seed(messages)
        if response_model is SurveyAnswer:
            # достаём question_id из промпта (мок-эвристика)
            qid = next((q for q in ("eqwlth", "helppoor", "helpnot", "getahead")
                        if q in (messages[-1].get("content", ""))), "eqwlth")
            from config import SCALES
            scale = SCALES[qid]
            val = scale[s % len(scale)]
            return SurveyAnswer(question_id=qid, answer_value=val,
                                rationale="(mock) ответ исходя из профиля",
                                confidence=0.5 + (s % 50) / 100)
        if response_model is JudgeVerdict:
            return JudgeVerdict(coherent=(s % 5 != 0),
                                hallucinated_reasoning=(s % 11 == 0),
                                issue="" if s % 5 else "(mock) слабая связь с профилем")
        if response_model is AmbiguityFlag:
            return AmbiguityFlag(ambiguous=(s % 7 == 0),
                                 reason="(mock) формулировка допускает трактовки"
                                 if s % 7 == 0 else "")
        raise TypeError(f"mock не умеет {response_model}")


class _MockChat:
    def __init__(self):
        self.completions = _MockCompletions()


class MockClient:
    def __init__(self):
        self.chat = _MockChat()


def make_mock_client() -> MockClient:
    return MockClient()
