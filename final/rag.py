"""
Мини-RAG: извлекаем релевантный фрагмент кодбука (формулировка + шкала вопроса),
чтобы подложить его в промпт персоне. Так модель отвечает по реальной анкете GSS,
а не по выдуманной шкале.

Реализация руками (без LangChain): TF-IDF поверх блоков codebook.md, косинусная
близость. По умолчанию ищем по question_id, но retrieve() принимает любой текст —
так RAG работает и для свободных запросов интервьюера.
"""
from __future__ import annotations

import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import ROOT


class CodebookRAG:
    def __init__(self, codebook_path: Path | None = None):
        path = codebook_path or (ROOT / "codebook.md")
        text = path.read_text(encoding="utf-8")
        # Делим на блоки по заголовкам "## "
        chunks = re.split(r"\n##\s+", text)
        self.docs: list[dict] = []
        for ch in chunks:
            ch = ch.strip()
            if not ch or ch.startswith("# "):
                continue
            # первый токен заголовка вида "eqwlth — ..." это id вопроса
            qid = ch.split(" ", 1)[0].strip().lower()
            self.docs.append({"qid": qid, "text": ch})
        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform([d["text"] for d in self.docs])

    def by_id(self, question_id: str) -> str:
        """Прямой доступ по id вопроса (основной путь)."""
        for d in self.docs:
            if d["qid"] == question_id.lower():
                return d["text"]
        # фолбэк — семантический поиск
        return self.retrieve(question_id, k=1)[0]

    def retrieve(self, query: str, k: int = 1) -> list[str]:
        """Семантический поиск k ближайших блоков по тексту запроса."""
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.matrix)[0]
        top = sims.argsort()[::-1][:k]
        return [self.docs[i]["text"] for i in top]


if __name__ == "__main__":
    rag = CodebookRAG()
    print("Вопросов в кодбуке:", [d["qid"] for d in rag.docs])
    print("\n--- by_id('eqwlth') ---\n", rag.by_id("eqwlth")[:200])
