from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, List

from .models import Annotation, DatasetConfig, TokenAssignment, User
from .segmenter import UzbekMorphSegmenter

_SEGMENTER_CACHE: dict[tuple[int, str], UzbekMorphSegmenter] = {}


def detect_delimiter(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return ","
    return "\t"


def load_words_from_dataset(dataset: DatasetConfig) -> List[str]:
    path = Path(dataset.tokens_file.path)
    delimiter = detect_delimiter(path)
    words: List[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

    if not rows:
        return words

    header = [col.strip().lower() for col in rows[0]]
    start_idx = 1 if "word" in header or "count" in header else 0
    word_col = header.index("word") if "word" in header else (1 if len(rows[0]) > 1 else 0)

    for row in rows[start_idx:]:
        if len(row) <= word_col:
            continue
        word = row[word_col].strip()
        if word:
            words.append(word)
    return words


def get_active_dataset() -> DatasetConfig | None:
    return DatasetConfig.objects.filter(is_active=True).order_by("-created_at").first()


def get_segmenter(dataset: DatasetConfig) -> UzbekMorphSegmenter:
    cache_key = (dataset.pk, str(dataset.updated_at.timestamp()))
    if cache_key not in _SEGMENTER_CACHE:
        _SEGMENTER_CACHE.clear()
        _SEGMENTER_CACHE[cache_key] = UzbekMorphSegmenter(Path(dataset.suffix_file.path))
    return _SEGMENTER_CACHE[cache_key]


def update_dataset_token_count(dataset: DatasetConfig) -> int:
    words = load_words_from_dataset(dataset)
    dataset.token_count = len(words)
    dataset.save(update_fields=["token_count", "updated_at"])
    return dataset.token_count


def generate_assignments(dataset: DatasetConfig, reset: bool = False) -> int:
    annotators = list(User.objects.filter(role="annotator", is_active=True).order_by("id"))
    if not annotators:
        return 0

    words = load_words_from_dataset(dataset)
    if reset:
        TokenAssignment.objects.filter(dataset=dataset).delete()

    existing = TokenAssignment.objects.filter(dataset=dataset).exists()
    if existing and not reset:
        return TokenAssignment.objects.filter(dataset=dataset).count()

    objs: list[TokenAssignment] = []
    if dataset.assignment_mode == "shared":
        for user in annotators:
            for idx, word in enumerate(words):
                objs.append(TokenAssignment(dataset=dataset, user=user, token_index=idx, word=word, mode="shared"))
    else:
        for idx, word in enumerate(words):
            user = annotators[idx % len(annotators)]
            objs.append(TokenAssignment(dataset=dataset, user=user, token_index=idx, word=word, mode="individual"))

    TokenAssignment.objects.bulk_create(objs, ignore_conflicts=True)
    if dataset.token_count != len(words):
        dataset.token_count = len(words)
        dataset.save(update_fields=["token_count", "updated_at"])
    return len(objs)


def get_user_assignments(user: User, dataset: DatasetConfig) -> List[TokenAssignment]:
    return list(TokenAssignment.objects.filter(user=user, dataset=dataset).order_by("token_index", "id"))


def refresh_user_stats(user: User) -> None:
    today = date.today()
    user.total_annotations = Annotation.objects.filter(user=user).count()
    user.today_annotations = Annotation.objects.filter(user=user, created_at__date=today).count()
    user.last_activity = Annotation.objects.filter(user=user).order_by("-created_at").values_list("created_at__date", flat=True).first()
    user.save(update_fields=["total_annotations", "today_annotations", "last_activity"])


def latest_annotations_for_token(dataset: DatasetConfig, token_index: int) -> List[Annotation]:
    qs = Annotation.objects.filter(dataset=dataset, token_index=token_index).select_related("user").order_by("user_id", "-created_at")
    latest_by_user: dict[int, Annotation] = {}
    for ann in qs:
        if ann.user_id not in latest_by_user:
            latest_by_user[ann.user_id] = ann
    return list(latest_by_user.values())


def annotation_rows_for_export(queryset: Iterable[Annotation]) -> list[dict]:
    rows = []
    for ann in queryset:
        rows.append(
            {
                "id": ann.id,
                "username": ann.user.username,
                "token_index": ann.token_index,
                "word": ann.word,
                "action": ann.action,
                "strategy": ann.strategy,
                "segments": ann.segments,
                "tags": ann.tags,
                "subtypes": ann.subtypes,
                "codes": ann.codes,
                "created_at": ann.created_at.isoformat(timespec="seconds"),
            }
        )
    return rows
