"""Load YAML curriculum, facts, and glossary from content/."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from bot.config import CONTENT_DIR, DIAGRAMS_DIR


@dataclass(frozen=True)
class Lesson:
    title: str
    body: str
    simple: str


@dataclass(frozen=True)
class QuizItem:
    question: str
    options: tuple[str, ...]
    answer: int
    explanation: str


@dataclass(frozen=True)
class Module:
    id: str
    title: str
    emoji: str
    blurb: str
    lessons: tuple[Lesson, ...]
    quizzes: tuple[QuizItem, ...]


@dataclass(frozen=True)
class Curriculum:
    modules: tuple[Module, ...]
    facts: tuple[str, ...]
    glossary: dict[str, str] = field(default_factory=dict)

    def by_id(self, module_id: str) -> Module | None:
        for mod in self.modules:
            if mod.id == module_id:
                return mod
        return None

    def lookup_term(self, word: str) -> tuple[str, str] | None:
        """Exact, then case-insensitive, then substring match on glossary keys."""
        raw = (word or "").strip()
        if not raw:
            return None
        if raw in self.glossary:
            return raw, self.glossary[raw]
        lowered = raw.lower()
        for key, defn in self.glossary.items():
            if key.lower() == lowered:
                return key, defn
        hits = [
            (key, defn)
            for key, defn in self.glossary.items()
            if lowered in key.lower() or lowered in defn.lower()
        ]
        if len(hits) == 1:
            return hits[0]
        if hits:
            # Prefer key substring matches over definition matches
            key_hits = [h for h in hits if lowered in h[0].lower()]
            if key_hits:
                key_hits.sort(key=lambda h: len(h[0]))
                return key_hits[0]
            hits.sort(key=lambda h: len(h[0]))
            return hits[0]
        return None

    def suggest_terms(self, word: str, limit: int = 5) -> list[str]:
        needle = (word or "").strip().lower()
        if not needle:
            return []
        scored: list[tuple[int, str]] = []
        for key in self.glossary:
            k = key.lower()
            if needle in k:
                scored.append((0, key))
            elif k.startswith(needle[:3]) and len(needle) >= 3:
                scored.append((1, key))
        scored.sort(key=lambda t: (t[0], len(t[1])))
        # unique preserve order
        out: list[str] = []
        for _, key in scored:
            if key not in out:
                out.append(key)
            if len(out) >= limit:
                break
        return out

    def find_module_for_term(self, term: str) -> str | None:
        """Best-effort: return module id whose lessons mention the term."""
        needle = (term or "").strip().lower()
        if not needle or len(needle) < 2:
            return None
        best_id: str | None = None
        best_score = 0
        for mod in self.modules:
            score = 0
            blob_title = f"{mod.title} {mod.blurb}".lower()
            if needle in blob_title:
                score += 5
            for lesson in mod.lessons:
                text = f"{lesson.title} {lesson.body} {lesson.simple}".lower()
                if needle in text:
                    score += 2 + text.count(needle)
            for q in mod.quizzes:
                qblob = f"{q.question} {q.explanation}".lower()
                if needle in qblob:
                    score += 1
            if score > best_score:
                best_score = score
                best_id = mod.id
        return best_id if best_score > 0 else None



def _load_yaml(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        raise ValueError(f"Empty YAML file: {path}")
    return data


def _parse_module(raw: dict) -> Module:
    lessons = tuple(
        Lesson(title=item["title"], body=item["body"], simple=item["simple"])
        for item in raw["lessons"]
    )
    quizzes = tuple(
        QuizItem(
            question=item["question"],
            options=tuple(item["options"]),
            answer=int(item["answer"]),
            explanation=item["explanation"],
        )
        for item in raw["quizzes"]
    )
    if len(lessons) < 4:
        raise ValueError(f"Module {raw['id']} needs at least 4 lessons")
    if len(quizzes) < 5:
        raise ValueError(f"Module {raw['id']} needs at least 5 quiz questions")
    for q in quizzes:
        if not (0 <= q.answer < len(q.options)):
            raise ValueError(f"Bad answer index in {raw['id']}: {q.question!r}")
        if len(q.options) < 2:
            raise ValueError(f"Quiz needs options in {raw['id']}: {q.question!r}")
        for opt in q.options:
            if not isinstance(opt, str):
                raise ValueError(
                    f"Quiz option must be a string in {raw['id']}: {opt!r}"
                )
            if len(opt) > 61:
                raise ValueError(
                    f"Quiz option too long for Telegram buttons in {raw['id']}: {opt!r}"
                )
    return Module(
        id=raw["id"],
        title=raw["title"],
        emoji=raw.get("emoji", "✈️"),
        blurb=raw["blurb"],
        lessons=lessons,
        quizzes=quizzes,
    )


@lru_cache(maxsize=1)
def load_curriculum() -> Curriculum:
    modules_dir = CONTENT_DIR / "modules"
    paths = sorted(modules_dir.glob("*.yaml"))
    if not paths:
        raise FileNotFoundError(f"No module YAML files in {modules_dir}")
    modules = tuple(_parse_module(_load_yaml(p)) for p in paths)

    facts_raw = _load_yaml(CONTENT_DIR / "facts.yaml")
    facts = tuple(str(x) for x in facts_raw["facts"])

    gloss_raw = _load_yaml(CONTENT_DIR / "glossary.yaml")
    glossary = {str(k): str(v) for k, v in gloss_raw["terms"].items()}

    ids = [m.id for m in modules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate module ids: {ids}")
    return Curriculum(modules=modules, facts=facts, glossary=glossary)


def diagram_path(module_id: str) -> Path | None:
    """Return path to a module diagram image if one exists under content/diagrams/."""
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = DIAGRAMS_DIR / f"{module_id}{ext}"
        if candidate.is_file():
            return candidate
    return None
