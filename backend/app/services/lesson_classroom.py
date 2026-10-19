from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.grammar import get_grammar_topic
from app.models.lesson import Lesson
from app.models.lesson_classroom_pack import LessonClassroomPack
from app.schemas.classroom import (
    AnnotationEvent,
    ClassroomBeat,
    ClassroomDeck,
    ClassroomGrammarTable,
    ClassroomPack,
    ClassroomPackLLMResult,
    LectureSegment,
    SlideFrame,
)
from app.services.language_helpers import get_language_name
from app.services.llm_adapter import (
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    llm_adapter,
)
from app.services.prompts.classroom import build_classroom_pack_prompt

logger = logging.getLogger(__name__)

EXPLANATION_CHUNK_CHARS = 500
GENERATOR_VERSION = "1"
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def chunk_text(text: str, max_chars: int = EXPLANATION_CHUNK_CHARS) -> list[str]:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    sentences = _SENTENCE_SPLIT.split(cleaned)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        piece = sentence.strip()
        if not piece:
            continue
        if len(piece) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(piece), max_chars):
                chunks.append(piece[start : start + max_chars].strip())
            continue
        candidate = f"{current} {piece}".strip() if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def lesson_content_hash(content: Any) -> str:
    payload = json.dumps(content if content is not None else {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_markdown_row(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return cells


def _is_markdown_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) is not None for cell in cells)


def extract_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            block.append(lines[index].strip())
            index += 1
        parsed = [_parse_markdown_row(line) for line in block]
        parsed = [row for row in parsed if row and not _is_markdown_separator(row)]
        if len(parsed) < 2:
            continue
        headers = parsed[0]
        rows = [row for row in parsed[1:] if any(cell.strip() for cell in row)]
        if not rows:
            continue
        width = len(headers)
        normalized = [row[:width] + [""] * max(0, width - len(row)) for row in rows]
        tables.append((headers, normalized))
    return tables


def lesson_grammar_refs(content: Any) -> list[str]:
    data = _as_dict(content)
    refs = data.get("grammar_refs")
    if isinstance(refs, list):
        return [item.strip() for item in refs if isinstance(item, str) and item.strip()]
    return []


def build_classroom_grammar_tables(
    lesson: Lesson,
    *,
    target_language: str,
) -> list[ClassroomGrammarTable]:
    tables: list[ClassroomGrammarTable] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for slug in lesson_grammar_refs(lesson.content):
        topic = get_grammar_topic(slug, target_language)
        if topic is None:
            continue
        for headers, rows in extract_markdown_tables(topic.explanation):
            key = (slug, tuple(headers))
            if key in seen:
                continue
            seen.add(key)
            tables.append(
                ClassroomGrammarTable(
                    slug=slug,
                    title=topic.title,
                    headers=headers,
                    rows=rows,
                )
            )
    return tables


def build_classroom_deck(
    lesson: Lesson,
    *,
    target_language: str,
) -> ClassroomDeck:
    content = _as_dict(lesson.content)
    explanation = _as_dict(content.get("explanation"))
    beats: list[ClassroomBeat] = []

    intro_text = lesson.title.strip() or "Lesson"
    beats.append(
        ClassroomBeat(
            id="intro",
            kind="intro",
            title=lesson.lesson_type or None,
            primary_text=intro_text,
            secondary_text=None,
            narration_text=intro_text,
        )
    )

    explanation_text = explanation.get("text")
    if isinstance(explanation_text, str) and explanation_text.strip():
        for index, chunk in enumerate(chunk_text(explanation_text)):
            beats.append(
                ClassroomBeat(
                    id=f"explanation-{index}",
                    kind="explanation",
                    title=None,
                    primary_text=chunk,
                    secondary_text=None,
                    narration_text=chunk,
                )
            )

    for index, point in enumerate(_as_str_list(explanation.get("key_points"))):
        beats.append(
            ClassroomBeat(
                id=f"keypoint-{index}",
                kind="key_point",
                title=None,
                primary_text=point,
                secondary_text=None,
                narration_text=point,
            )
        )

    examples = explanation.get("examples")
    if isinstance(examples, list):
        example_index = 0
        for raw in examples:
            if not isinstance(raw, dict):
                continue
            sentence = raw.get("sentence")
            if not isinstance(sentence, str) or not sentence.strip():
                continue
            note = raw.get("note")
            secondary = note.strip() if isinstance(note, str) and note.strip() else None
            narration = sentence.strip() if not secondary else f"{sentence.strip()}. {secondary}"
            beats.append(
                ClassroomBeat(
                    id=f"example-{example_index}",
                    kind="example",
                    title=None,
                    primary_text=sentence.strip(),
                    secondary_text=secondary,
                    narration_text=narration,
                )
            )
            example_index += 1

    vocabulary = content.get("vocabulary")
    if isinstance(vocabulary, list):
        vocab_index = 0
        for raw in vocabulary:
            if not isinstance(raw, dict):
                continue
            word = raw.get("word")
            if not isinstance(word, str) or not word.strip():
                continue
            example = raw.get("example")
            definition = raw.get("definition")
            secondary_parts: list[str] = []
            if isinstance(definition, str) and definition.strip():
                secondary_parts.append(definition.strip())
            if isinstance(example, str) and example.strip():
                secondary_parts.append(example.strip())
            secondary = " · ".join(secondary_parts) if secondary_parts else None
            narration_parts = [word.strip()]
            if isinstance(example, str) and example.strip():
                narration_parts.append(example.strip())
            beats.append(
                ClassroomBeat(
                    id=f"vocab-{vocab_index}",
                    kind="vocabulary",
                    title=None,
                    primary_text=word.strip(),
                    secondary_text=secondary,
                    narration_text=". ".join(narration_parts),
                )
            )
            vocab_index += 1

    closing = "Ready for practice"
    beats.append(
        ClassroomBeat(
            id="closing",
            kind="closing",
            title=None,
            primary_text=closing,
            secondary_text=None,
            narration_text=closing,
        )
    )

    return ClassroomDeck(
        lesson_id=lesson.id,
        study_plan_id=lesson.study_plan_id,
        target_language=target_language,
        title=lesson.title,
        cefr_level=lesson.cefr_level,
        lesson_type=lesson.lesson_type,
        beats=beats,
    )


def find_beat(deck: ClassroomDeck, beat_id: str) -> ClassroomBeat | None:
    return next((beat for beat in deck.beats if beat.id == beat_id), None)


def find_segment(pack: ClassroomPack, segment_id: str) -> LectureSegment | None:
    return next((segment for segment in pack.segments if segment.id == segment_id), None)


def find_slide(pack: ClassroomPack, slide_id: str) -> SlideFrame | None:
    return next((slide for slide in pack.slides if slide.id == slide_id), None)


def _slide_field_text(slide: SlideFrame, event: AnnotationEvent) -> str:
    if event.target_field == "title":
        return slide.title
    if event.target_field == "callout":
        return slide.callout or ""
    if event.target_field == "bullet" and event.target_index is not None:
        if 0 <= event.target_index < len(slide.bullets):
            return slide.bullets[event.target_index]
    return ""


def normalize_classroom_pack(
    raw: ClassroomPackLLMResult,
    *,
    lesson: Lesson,
    target_language: str,
    content_hash: str,
) -> ClassroomPack:
    slides_by_id = {slide.id: slide for slide in raw.slides}
    if not slides_by_id:
        raise ValueError("Classroom pack has no slides")

    segments: list[LectureSegment] = []
    for index, segment in enumerate(sorted(raw.segments, key=lambda item: item.order)):
        if segment.slide_id not in slides_by_id:
            raise ValueError(f"Unknown slide_id {segment.slide_id}")
        slide = slides_by_id[segment.slide_id]
        slide_body = " ".join([slide.title, *slide.bullets, slide.callout or ""]).strip()
        if (
            segment.kind in {"concept", "example_walkthrough", "contrast", "vocab_spotlight"}
            and segment.speech_text.strip()
            and slide_body
            and segment.speech_text.strip() == slide_body
        ):
            raise ValueError("speech_text must not equal slide body")
        segments.append(
            LectureSegment(
                id=segment.id or f"seg-{index}",
                order=index,
                kind=segment.kind,
                speech_text=segment.speech_text.strip(),
                slide_id=segment.slide_id,
                annotation_event_ids=list(segment.annotation_event_ids),
            )
        )
    if not segments:
        raise ValueError("Classroom pack has no segments")

    segment_ids = {segment.id for segment in segments}
    annotations: list[AnnotationEvent] = []
    for event in raw.annotations:
        if event.segment_id not in segment_ids:
            continue
        segment = next(item for item in segments if item.id == event.segment_id)
        slide = slides_by_id[segment.slide_id]
        field_text = _slide_field_text(slide, event)
        substring = event.substring.strip() if event.substring else None
        if event.op in {"highlight", "underline"} and substring and substring not in field_text:
            substring = None
            if field_text:
                substring = field_text[: min(40, len(field_text))]
        payload = event.payload.strip()
        if event.op == "margin_note" and not payload:
            continue
        if event.op in {"highlight", "underline"} and not (substring or payload):
            continue
        annotations.append(
            AnnotationEvent(
                id=event.id,
                segment_id=event.segment_id,
                at=event.at,
                speech_fraction=event.speech_fraction,
                op=event.op,
                target_field=event.target_field,
                target_index=event.target_index,
                substring=substring,
                payload=payload or (substring or ""),
            )
        )

    annotation_ids = {item.id for item in annotations}
    fixed_segments: list[LectureSegment] = []
    for segment in segments:
        fixed_segments.append(
            segment.model_copy(
                update={
                    "annotation_event_ids": [
                        event_id
                        for event_id in segment.annotation_event_ids
                        if event_id in annotation_ids
                    ]
                }
            )
        )

    slides = [
        SlideFrame(
            id=slide.id,
            title=slide.title.strip(),
            bullets=[item.strip() for item in slide.bullets if item.strip()][:5],
            callout=slide.callout.strip() if slide.callout else None,
            reveal_steps=max(1, min(slide.reveal_steps, 6)),
        )
        for slide in raw.slides
    ]

    return ClassroomPack(
        lesson_id=lesson.id,
        study_plan_id=lesson.study_plan_id,
        target_language=target_language,
        title=lesson.title,
        cefr_level=lesson.cefr_level,
        lesson_type=lesson.lesson_type,
        content_hash=content_hash,
        generator_version=GENERATOR_VERSION,
        segments=fixed_segments,
        slides=slides,
        annotations=annotations,
    )


async def get_stored_pack(
    db: AsyncSession,
    lesson: Lesson,
    *,
    target_language: str,
) -> ClassroomPack | None:
    content_hash = lesson_content_hash(lesson.content)
    row = await db.get(LessonClassroomPack, lesson.id)
    if row is None:
        return None
    if row.content_hash != content_hash or row.generator_version != GENERATOR_VERSION:
        return None
    try:
        pack = ClassroomPack.model_validate(row.payload)
    except Exception:
        logger.exception("Invalid classroom pack payload for lesson %s", lesson.id)
        return None
    if pack.target_language != target_language:
        return None
    return pack


async def save_classroom_pack(db: AsyncSession, pack: ClassroomPack) -> ClassroomPack:
    row = await db.get(LessonClassroomPack, pack.lesson_id)
    payload = pack.model_dump()
    if row is None:
        row = LessonClassroomPack(
            lesson_id=pack.lesson_id,
            content_hash=pack.content_hash,
            generator_version=pack.generator_version,
            payload=payload,
        )
        db.add(row)
    else:
        row.content_hash = pack.content_hash
        row.generator_version = pack.generator_version
        row.payload = payload
    await db.commit()
    return pack


async def generate_classroom_pack(
    lesson: Lesson,
    *,
    target_language: str,
) -> ClassroomPack:
    lesson_id = lesson.id
    study_plan_id = lesson.study_plan_id
    title = lesson.title
    cefr_level = lesson.cefr_level
    lesson_type = lesson.lesson_type
    content = lesson.content
    content_hash = lesson_content_hash(content)
    prompt = build_classroom_pack_prompt(
        target_language_name=get_language_name(target_language),
        lesson_title=title,
        cefr_level=cefr_level,
        lesson_type=lesson_type,
        lesson_content_json=json.dumps(content or {}, ensure_ascii=False),
    )
    try:
        result = await llm_adapter.structured_output(
            [{"role": "user", "content": prompt}],
            ClassroomPackLLMResult,
        )
    except (LLMError, LLMTimeoutError, LLMUnavailableError):
        raise
    raw = (
        result
        if isinstance(result, ClassroomPackLLMResult)
        else ClassroomPackLLMResult.model_validate(result)
    )
    snapshot = type(
        "LessonSnapshot",
        (),
        {
            "id": lesson_id,
            "study_plan_id": study_plan_id,
            "title": title,
            "cefr_level": cefr_level,
            "lesson_type": lesson_type,
            "content": content,
        },
    )()
    return normalize_classroom_pack(
        raw,
        lesson=snapshot,
        target_language=target_language,
        content_hash=content_hash,
    )


async def generate_and_store_classroom_pack(
    db: AsyncSession,
    lesson_id: int,
    *,
    target_language: str,
) -> ClassroomPack | None:
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if lesson is None:
        return None
    existing = await get_stored_pack(db, lesson, target_language=target_language)
    if existing is not None:
        return existing
    pack = await generate_classroom_pack(lesson, target_language=target_language)
    return await save_classroom_pack(db, pack)
