"""
The distilled moderation classifier (see ai/distill/).

A logistic-regression head over text-embedding-3-small vectors, loaded from
plain JSON (no pickles). It only ever short-circuits the LLM pipeline on a
confident "allow": anything else, and anything stage 0 flagged, still goes to
the policy model. Inference is a few thousand multiply-adds in pure Python.
"""
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Student:
    classes: list[str]
    coef: list[list[float]]
    intercept: list[float]
    temperature: float
    allow_threshold: float
    embedding_model: str

    def probabilities(self, vector: list[float]) -> dict[str, float]:
        logits = [sum(w * x for w, x in zip(row, vector, strict=True)) + b
                  for row, b in zip(self.coef, self.intercept, strict=True)]
        scaled = [z / self.temperature for z in logits]
        top = max(scaled)
        exps = [math.exp(z - top) for z in scaled]
        total = sum(exps)
        return {c: e / total for c, e in zip(self.classes, exps, strict=True)}

    def confident_allow(self, vector: list[float]) -> tuple[bool, float]:
        p = self.probabilities(vector)['allow']
        return p >= self.allow_threshold, p


def load(path: str | None) -> Student | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        student = Student(classes=data['classes'], coef=data['coef'], intercept=data['intercept'],
                          temperature=float(data['temperature']), allow_threshold=float(data['allow_threshold']),
                          embedding_model=data['embedding_model'])
    except (OSError, ValueError, KeyError, TypeError):
        logger.exception('Could not load the distilled moderation model from %s', path)
        return None
    if student.classes[0] != 'allow' or student.allow_threshold > 1:
        logger.warning('Distilled model has no usable allow threshold; not using it')
        return None
    return student
