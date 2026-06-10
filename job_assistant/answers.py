"""Reusable application question and answer bank."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import re

from .models import ConfigError


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass(frozen=True)
class SavedAnswer:
    question: str
    answer: str
    options: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SavedAnswer":
        question = str(value.get("question", "")).strip()
        answer = str(value.get("answer", "")).strip()
        if not question:
            raise ConfigError("Saved answer requires a question")
        if not answer:
            raise ConfigError(f"Saved answer for '{question}' requires an answer")
        return cls(
            question=question,
            answer=answer,
            options=[str(item).strip() for item in value.get("options", []) if str(item).strip()],
            keywords=[str(item).strip() for item in value.get("keywords", []) if str(item).strip()],
        )

    def score(self, question: str, options: list[str] | None = None) -> int:
        normalized_question = _normalize(question)
        normalized_options = {_normalize(option) for option in options or []}
        score = 0
        saved_question = _normalize(self.question)
        if saved_question == normalized_question:
            score += 100
        elif saved_question and saved_question in normalized_question:
            score += 40
        elif normalized_question and normalized_question in saved_question:
            score += 30

        for keyword in self.keywords:
            normalized_keyword = _normalize(keyword)
            if normalized_keyword and normalized_keyword in normalized_question:
                score += 20

        saved_options = {_normalize(option) for option in self.options}
        if normalized_options and saved_options:
            score += 25 * len(normalized_options & saved_options)
        return score


class AnswerBank:
    """JSON-backed answer store for repeated application questions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.answers = self._load()

    def _load(self) -> list[SavedAnswer]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid answer bank JSON in {self.path}: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("answers", [])
        if not isinstance(data, list):
            raise ConfigError("Answer bank must be a list or an object with an answers list")
        return [SavedAnswer.from_dict(item) for item in data]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "answers": [
                {
                    "question": answer.question,
                    "answer": answer.answer,
                    "options": answer.options,
                    "keywords": answer.keywords,
                }
                for answer in self.answers
            ]
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def add(
        self,
        question: str,
        answer: str,
        options: list[str] | None = None,
        keywords: list[str] | None = None,
        replace: bool = False,
    ) -> None:
        normalized_question = _normalize(question)
        new_answer = SavedAnswer(
            question=question.strip(),
            answer=answer.strip(),
            options=[item.strip() for item in options or [] if item.strip()],
            keywords=[item.strip() for item in keywords or [] if item.strip()],
        )
        kept = []
        replaced = False
        for saved in self.answers:
            if _normalize(saved.question) == normalized_question:
                if replace:
                    replaced = True
                    continue
                raise ConfigError(f"Answer already exists for question: {question}")
            kept.append(saved)
        kept.append(new_answer)
        self.answers = kept
        if replace and not replaced:
            self.answers = kept

    def match(self, question: str, options: list[str] | None = None) -> SavedAnswer | None:
        scored = [(answer.score(question, options), answer) for answer in self.answers]
        scored = [item for item in scored if item[0] > 0]
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1].question))
        return scored[0][1]

    def suggestions(self, questions: list[tuple[str, list[str]]]) -> dict[str, str]:
        suggested: dict[str, str] = {}
        for question, options in questions:
            match = self.match(question, options)
            if match:
                suggested[question] = match.answer
        return suggested
