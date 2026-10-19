from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ClassroomBeat(BaseModel):
    id: str
    kind: Literal[
        "intro",
        "explanation",
        "key_point",
        "example",
        "vocabulary",
        "closing",
    ]
    title: str | None = None
    primary_text: str
    secondary_text: str | None = None
    narration_text: str


class ClassroomDeck(BaseModel):
    lesson_id: int
    study_plan_id: int
    target_language: str
    title: str
    cefr_level: str
    lesson_type: str
    beats: list[ClassroomBeat]


class ClassroomClarifyRequest(BaseModel):
    beat_id: str = Field(min_length=1, max_length=64)
    action: Literal["rephrase", "more_examples"]
    focus_text: str | None = Field(default=None, max_length=500)
    ui_locale: str | None = Field(default=None, max_length=16)
    segment_id: str | None = Field(default=None, max_length=64)


class ClassroomAnnotationOp(BaseModel):
    beat_id: str
    type: Literal["highlight", "margin_note", "underline"]
    payload: str = Field(min_length=1, max_length=1000)


class ClassroomClarifyAnnotation(BaseModel):
    type: Literal["highlight", "margin_note", "underline"]
    payload: str


class ClassroomClarifyLLMResult(BaseModel):
    spoken_text: str
    display_text: str
    annotations: list[ClassroomClarifyAnnotation] = []


class ClassroomClarifyResponse(BaseModel):
    spoken_text: str
    display_text: str
    annotations: list[ClassroomAnnotationOp] = []


LectureSegmentKind = Literal[
    "hook",
    "concept",
    "example_walkthrough",
    "contrast",
    "vocab_spotlight",
    "cfu",
    "summary",
    "handoff",
]


class LectureSegment(BaseModel):
    id: str
    order: int
    kind: LectureSegmentKind
    speech_text: str = Field(min_length=1, max_length=2000)
    slide_id: str
    annotation_event_ids: list[str] = []


class SlideFrame(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=200)
    bullets: list[str] = Field(default_factory=list, max_length=5)
    callout: str | None = Field(default=None, max_length=500)
    reveal_steps: int = Field(default=1, ge=1, le=6)


class AnnotationEvent(BaseModel):
    id: str
    segment_id: str
    at: Literal["segment_start", "speech_fraction"] = "segment_start"
    speech_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    op: Literal["highlight", "underline", "margin_note", "clear"]
    target_field: Literal["title", "callout", "bullet"] = "title"
    target_index: int | None = Field(default=None, ge=0, le=4)
    substring: str | None = Field(default=None, max_length=300)
    payload: str = Field(default="", max_length=1000)

    @field_validator("target_field", mode="before")
    @classmethod
    def normalize_target_field(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {"bullets", "bullet"}:
            return "bullet"
        return value

    @field_validator("at", mode="before")
    @classmethod
    def normalize_at(cls, value: Any) -> Any:
        if isinstance(value, str):
            cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
            if cleaned in {"segment_start", "start"}:
                return "segment_start"
            if cleaned in {"speech_fraction", "fraction"}:
                return "speech_fraction"
        return value


class ClassroomPack(BaseModel):
    lesson_id: int
    study_plan_id: int
    target_language: str
    title: str
    cefr_level: str
    lesson_type: str
    content_hash: str
    generator_version: str
    segments: list[LectureSegment]
    slides: list[SlideFrame]
    annotations: list[AnnotationEvent]


class ClassroomPackLLMResult(BaseModel):
    segments: list[LectureSegment]
    slides: list[SlideFrame]
    annotations: list[AnnotationEvent] = []


class ClassroomGrammarTable(BaseModel):
    slug: str
    title: str
    headers: list[str]
    rows: list[list[str]]


class ClassroomSessionResponse(BaseModel):
    status: Literal["ready", "generating", "fallback"]
    mode: Literal["lecture", "reading"]
    pack: ClassroomPack | None = None
    fallback_deck: ClassroomDeck | None = None
    preparing: bool = False
    grammar_tables: list[ClassroomGrammarTable] = []


class ClassroomPackStatusResponse(BaseModel):
    status: Literal["ready", "generating", "missing", "failed"]
    pack: ClassroomPack | None = None


class ClassroomGenerateResponse(BaseModel):
    status: Literal["ready", "generating"]
    pack: ClassroomPack | None = None
