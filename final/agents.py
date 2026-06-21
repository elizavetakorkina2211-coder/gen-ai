"""
Три LLM-роли проекта:

  respond()    — синтетическая ПЕРСОНА отвечает на вопрос анкеты (silicon sampling).
  judge()      — LLM-AS-JUDGE: согласован ли ответ с профилем, есть ли выдумки.
  interview()  — агент-ИНТЕРВЬЮЕР (мультиагент): ищет двусмысленность вопроса
                 для конкретной персоны до того, как она отвечает.

Все ответы — структурированные (response_model + max_retries), как в семинарах.
RAG-контекст (формулировка вопроса) приходит снаружи из rag.CodebookRAG.
"""
from __future__ import annotations

from schemas import AmbiguityFlag, JudgeVerdict, Persona, SurveyAnswer

RESPONDENT_SYSTEM = """Ты вживаешься в роль конкретного человека по его
демографическому профилю и отвечаешь на вопрос социального опроса ИМЕННО так,
как ответил бы такой человек в США. Не усредняй, не уклоняйся в «нейтрально»,
если профиль склоняет к краю шкалы. Отвечай ТОЛЬКО числовым кодом из шкалы,
указанной в материалах вопроса, и коротким обоснованием от первого лица."""

JUDGE_SYSTEM = """Ты — методолог опросов. Тебе дают профиль человека, вопрос и
его ответ с обоснованием. Оцени ДВА пункта: (1) coherent — правдоподобно ли,
что человек с таким профилем так ответит; (2) hallucinated_reasoning — есть ли
в обосновании выдуманные числа, факты или ссылки на несуществующее. Будь строгим."""

INTERVIEWER_SYSTEM = """Ты — агент-интервьюер, который перед опросом проверяет
вопрос на двусмысленность ДЛЯ КОНКРЕТНОГО респондента. Двусмысленность — когда
формулировка/шкала может быть понята по-разному (или термин незнаком профилю).
Это пилот анкеты: твоя цель — поймать плохие вопросы, а не ответить на них."""


def _persona_block(p: Persona) -> str:
    fields = [
        ("возраст", p.age), ("пол", p.sex), ("раса", p.race),
        ("образование", p.degree), ("доход", p.income),
        ("партийность", p.partyid), ("полит. взгляды", p.polviews),
        ("регион", p.region),
    ]
    return "; ".join(f"{k}: {v}" for k, v in fields if v is not None)


def respond(client, model: str, persona: Persona, question_id: str,
            question_doc: str) -> SurveyAnswer:
    """ПЕРСОНА отвечает на вопрос. question_doc — текст из RAG (кодбук)."""
    msgs = [
        {"role": "system", "content": RESPONDENT_SYSTEM},
        {"role": "user", "content": (
            f"Профиль респондента: {_persona_block(persona)}\n\n"
            f"Вопрос анкеты [{question_id}]:\n{question_doc}\n\n"
            f"Ответь как этот человек. answer_value — строго код из шкалы выше."
        )},
    ]
    return client.chat.completions.create(
        model=model, response_model=SurveyAnswer, max_retries=2,
        temperature=0.7, messages=msgs,  # temperature>0: люди разные
    )


def judge(client, model: str, persona: Persona, question_doc: str,
          answer: SurveyAnswer) -> JudgeVerdict:
    msgs = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": (
            f"Профиль: {_persona_block(persona)}\n"
            f"Вопрос:\n{question_doc}\n"
            f"Ответ: код={answer.answer_value}, обоснование: «{answer.rationale}»"
        )},
    ]
    return client.chat.completions.create(
        model=model, response_model=JudgeVerdict, max_retries=2,
        temperature=0.0, messages=msgs,
    )


def interview(client, model: str, persona: Persona, question_id: str,
              question_doc: str) -> AmbiguityFlag:
    msgs = [
        {"role": "system", "content": INTERVIEWER_SYSTEM},
        {"role": "user", "content": (
            f"Профиль: {_persona_block(persona)}\n"
            f"Вопрос [{question_id}]:\n{question_doc}\n"
            f"Двусмыслен ли этот вопрос для данного респондента?"
        )},
    ]
    return client.chat.completions.create(
        model=model, response_model=AmbiguityFlag, max_retries=2,
        temperature=0.0, messages=msgs,
    )
