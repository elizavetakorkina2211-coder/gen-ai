"""
Структурированный вывод проекта: Pydantic-схемы с валидаторами.

Бизнес-инвариант (field_validator):
  ответ респондента ДОЛЖЕН лежать в допустимой шкале своего вопроса (config.SCALES).
  Это ловит галлюцинации шкалы — когда модель выдаёт код, которого в анкете нет.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from config import SCALES


class Persona(BaseModel):
    """Демографический профиль одного «испытуемого» из GSS."""

    respondent_id: int
    age: Optional[int] = None
    sex: Optional[str] = None
    race: Optional[str] = None
    degree: Optional[str] = None
    income: Optional[str] = None      # человекочитаемая категория дохода
    partyid: Optional[str] = None
    polviews: Optional[str] = None
    region: Optional[str] = None


class SurveyAnswer(BaseModel):
    """Структурированный ответ синтетической персоны на один вопрос анкеты."""

    question_id: str = Field(description="id вопроса, напр. 'eqwlth'")
    answer_value: int = Field(description="Числовой код ответа по шкале вопроса")
    rationale: str = Field(description="Короткое обоснование от лица персоны")
    confidence: float = Field(ge=0.0, le=1.0, description="Уверенность 0..1")

    @field_validator("rationale")
    @classmethod
    def rationale_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rationale не должен быть пустым")
        return v.strip()

    @model_validator(mode="after")
    def answer_in_scale(self) -> "SurveyAnswer":
        # БИЗНЕС-ИНВАРИАНТ: код ответа обязан быть в допустимой шкале вопроса.
        allowed = SCALES.get(self.question_id)
        if allowed is None:
            raise ValueError(f"неизвестный вопрос: {self.question_id}")
        if self.answer_value not in allowed:
            raise ValueError(
                f"ответ {self.answer_value} вне шкалы вопроса {self.question_id} "
                f"(допустимо: {allowed})"
            )
        return self


class JudgeVerdict(BaseModel):
    """Вердикт LLM-судьи о качестве ответа персоны."""

    coherent: bool = Field(description="Согласуется ли ответ с профилем персоны")
    hallucinated_reasoning: bool = Field(
        description="Есть ли в rationale выдуманные числа/факты/ложные ссылки"
    )
    issue: str = Field(default="", description="Одна фраза, что не так (если есть)")


class AmbiguityFlag(BaseModel):
    """Вывод агента-интервьюера: насколько вопрос двусмыслен для этой персоны."""

    ambiguous: bool = Field(description="Двусмыслен ли вопрос для данной персоны")
    reason: str = Field(default="", description="Чем именно двусмыслен")
