from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.classroom import (
    AnnotationEvent,
    ClassroomClarifyLLMResult,
    ClassroomPackLLMResult,
    LectureSegment,
    SlideFrame,
)
from app.services.lesson_classroom import (
    GENERATOR_VERSION,
    build_classroom_deck,
    build_classroom_grammar_tables,
    chunk_text,
    extract_markdown_tables,
    find_beat,
    get_stored_pack,
    lesson_content_hash,
    normalize_classroom_pack,
    save_classroom_pack,
)


def _sample_llm_pack() -> ClassroomPackLLMResult:
    return ClassroomPackLLMResult(
        slides=[
            SlideFrame(
                id="slide-hook",
                title="Pasado simple",
                bullets=["Una forma del pasado"],
                callout=None,
                reveal_steps=1,
            ),
            SlideFrame(
                id="slide-concept",
                title="Cómo se forma",
                bullets=["Raíz", "Terminación"],
                callout="Yo hablé.",
                reveal_steps=2,
            ),
        ],
        segments=[
            LectureSegment(
                id="seg-hook",
                order=0,
                kind="hook",
                speech_text="Hoy vamos a mirar el pasado simple juntos.",
                slide_id="slide-hook",
                annotation_event_ids=["ann-1"],
            ),
            LectureSegment(
                id="seg-concept",
                order=1,
                kind="concept",
                speech_text="Primero miramos la raíz, luego la terminación.",
                slide_id="slide-concept",
                annotation_event_ids=["ann-2"],
            ),
            LectureSegment(
                id="seg-hand",
                order=2,
                kind="handoff",
                speech_text="Ahora puedes practicar con los ejercicios.",
                slide_id="slide-hook",
                annotation_event_ids=[],
            ),
        ],
        annotations=[
            AnnotationEvent(
                id="ann-1",
                segment_id="seg-hook",
                at="segment_start",
                op="underline",
                target_field="title",
                substring="Pasado",
                payload="Pasado",
            ),
            AnnotationEvent(
                id="ann-2",
                segment_id="seg-concept",
                at="speech_fraction",
                speech_fraction=0.4,
                op="highlight",
                target_field="callout",
                substring="hablé",
                payload="hablé",
            ),
        ],
    )


def test_chunk_text_splits_long_explanation():
    text = " ".join(f"Sentence number {i}." for i in range(40))
    chunks = chunk_text(text, max_chars=80)
    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert "Sentence number 0." in chunks[0]
    assert any("Sentence number 39." in chunk for chunk in chunks)


def test_build_classroom_deck_deterministic_ids_and_optional_fields():
    lesson = SimpleNamespace(
        id=3,
        study_plan_id=9,
        title="Pasado simple",
        lesson_type="grammar",
        cefr_level="A2",
        content={
            "explanation": {
                "text": "Short explanation.",
                "key_points": ["Point A", "Point B", ""],
                "examples": [
                    {"sentence": "Yo hablé.", "note": "pretérito"},
                    {"sentence": "  "},
                    "ignore",
                ],
            },
            "vocabulary": [
                {
                    "word": "hablé",
                    "definition": "I spoke",
                    "example": "Yo hablé ayer.",
                },
                {"word": ""},
            ],
        },
    )
    deck = build_classroom_deck(lesson, target_language="es-ES")
    assert deck.lesson_id == 3
    assert deck.study_plan_id == 9
    assert deck.target_language == "es-ES"
    ids = [beat.id for beat in deck.beats]
    assert ids[0] == "intro"
    assert "explanation-0" in ids
    assert "keypoint-0" in ids
    assert "keypoint-1" in ids
    assert "example-0" in ids
    assert "vocab-0" in ids
    assert ids[-1] == "closing"
    assert find_beat(deck, "missing") is None
    assert find_beat(deck, "example-0").secondary_text == "pretérito"


def test_build_classroom_deck_tolerates_missing_content():
    lesson = SimpleNamespace(
        id=1,
        study_plan_id=2,
        title="Empty",
        lesson_type="vocabulary",
        cefr_level="A1",
        content=None,
    )
    deck = build_classroom_deck(lesson, target_language="en-GB")
    assert [beat.kind for beat in deck.beats] == ["intro", "closing"]


def test_extract_markdown_tables_parses_conjugation_grid():
    text = (
        "Intro text.\n\n"
        "| Persona | -ar (hablar) | -er (comer) |\n"
        "|--------|-------------|-------------|\n"
        "| yo | hablé | comí |\n"
        "| tú | hablaste | comiste |\n\n"
        "More text."
    )
    tables = extract_markdown_tables(text)
    assert len(tables) == 1
    headers, rows = tables[0]
    assert headers == ["Persona", "-ar (hablar)", "-er (comer)"]
    assert rows[0] == ["yo", "hablé", "comí"]
    assert rows[1][0] == "tú"


def test_build_classroom_grammar_tables_from_grammar_refs():
    lesson = SimpleNamespace(
        id=1,
        study_plan_id=2,
        title="Pasado",
        lesson_type="grammar",
        cefr_level="A2",
        content={
            "grammar_refs": ["preterito-indefinido-regular", "marcadores-temporales"],
            "explanation": {"text": "x", "key_points": [], "examples": []},
        },
    )
    tables = build_classroom_grammar_tables(lesson, target_language="es-ES")
    assert any(table.slug == "preterito-indefinido-regular" for table in tables)
    regular = next(
        table for table in tables if table.slug == "preterito-indefinido-regular"
    )
    assert "Persona" in regular.headers or "yo" in {
        cell for row in regular.rows for cell in row
    }
    assert any("hablé" in cell for row in regular.rows for cell in row)


def test_annotation_event_accepts_bullets_alias():
    event = AnnotationEvent(
        id="a1",
        segment_id="seg",
        at="segment_start",
        op="highlight",
        target_field="bullets",
        target_index=0,
        substring="hola",
        payload="hola",
    )
    assert event.target_field == "bullet"


def test_normalize_pack_keeps_speech_different_from_slide_and_valid_annotations():
    lesson = SimpleNamespace(
        id=11,
        study_plan_id=22,
        title="Pasado simple",
        lesson_type="grammar",
        cefr_level="A2",
        content={"explanation": {"text": "x"}},
    )
    pack = normalize_classroom_pack(
        _sample_llm_pack(),
        lesson=lesson,
        target_language="es-ES",
        content_hash="abc",
    )
    concept = next(segment for segment in pack.segments if segment.kind == "concept")
    slide = next(item for item in pack.slides if item.id == concept.slide_id)
    slide_body = " ".join([slide.title, *slide.bullets, slide.callout or ""])
    assert concept.speech_text != slide_body
    assert any(event.substring == "hablé" for event in pack.annotations)
    assert pack.generator_version == GENERATOR_VERSION


def test_normalize_pack_rejects_identical_speech_and_slide_body():
    lesson = SimpleNamespace(
        id=1,
        study_plan_id=2,
        title="T",
        lesson_type="grammar",
        cefr_level="A2",
        content={},
    )
    with pytest.raises(ValueError, match="speech_text"):
        normalize_classroom_pack(
            ClassroomPackLLMResult(
                slides=[
                    SlideFrame(
                        id="s1",
                        title="Hello world",
                        bullets=[],
                        callout=None,
                        reveal_steps=1,
                    )
                ],
                segments=[
                    LectureSegment(
                        id="seg",
                        order=0,
                        kind="concept",
                        speech_text="Hello world",
                        slide_id="s1",
                        annotation_event_ids=[],
                    )
                ],
                annotations=[],
            ),
            lesson=lesson,
            target_language="en-GB",
            content_hash="h",
        )


@pytest.mark.asyncio
async def test_classroom_deck_requires_auth(client):
    response = await client.get("/api/lessons/1/classroom/deck")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_classroom_deck_other_user_forbidden(client, test_user, db_session):
    from app.core.security import hash_password
    from app.models.user import User
    from tests.test_lessons_router import _create_lesson_with_plan

    owner = User(
        username="classroomowner",
        email="classroomowner@example.com",
        display_name="Owner",
        hashed_password=hash_password("ownerpass"),
        role="user",
        native_language="en",
        is_active=True,
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)
    lesson = await _create_lesson_with_plan(
        db_session,
        owner.id,
        content={"explanation": {"text": "Hola.", "key_points": [], "examples": []}},
    )
    _, headers = test_user
    response = await client.get(f"/api/lessons/{lesson.id}/classroom/deck", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_classroom_deck_includes_grammar_tables_from_refs(
    client, test_user, db_session
):
    from app.models.lesson import Lesson
    from app.schemas.exercise_generation import ExerciseGenerationState
    from tests.conftest import make_study_plan

    user, headers = test_user
    plan = await make_study_plan(
        db_session,
        user_id=user.id,
        target_language="es-ES",
        cefr_level="A2",
        goals=["grammar"],
        duration_weeks=4,
        days_per_week=4,
        current_unit="",
        generated_plan={},
        is_active=True,
    )
    lesson = Lesson(
        study_plan_id=plan.id,
        title="Pasado simple",
        lesson_type="grammar",
        cefr_level="A2",
        week_number=1,
        day_number=1,
        content={
            "grammar_refs": ["preterito-indefinido-regular"],
            "explanation": {"text": "Pasado.", "key_points": [], "examples": []},
        },
    )
    db_session.add(lesson)
    await db_session.commit()
    await db_session.refresh(lesson)

    with (
        patch(
            "app.routers.lesson_classroom.get_generation_state",
            new=AsyncMock(
                return_value=ExerciseGenerationState(generation_status="generating")
            ),
        ),
        patch(
            "app.routers.lesson_classroom.GenerationLease.acquire",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = await client.get(
            f"/api/lessons/{lesson.id}/classroom/deck", headers=headers
        )
    assert response.status_code == 200
    data = response.json()
    assert data["grammar_tables"]
    assert data["grammar_tables"][0]["slug"] == "preterito-indefinido-regular"
    assert any(
        "hablé" in cell
        for row in data["grammar_tables"][0]["rows"]
        for cell in row
    )


@pytest.mark.asyncio
async def test_classroom_deck_returns_fallback_while_generating(client, test_user, db_session):
    from app.schemas.exercise_generation import ExerciseGenerationState
    from tests.test_lessons_router import _create_lesson_with_plan

    user, headers = test_user
    lesson = await _create_lesson_with_plan(
        db_session,
        user.id,
        title="Unit one",
        content={
            "explanation": {
                "text": "We study the past.",
                "key_points": ["Regular -ar verbs"],
                "examples": [{"sentence": "Yo hablé.", "note": "note"}],
            },
            "vocabulary": [{"word": "ayer", "definition": "yesterday", "example": "Ayer."}],
        },
    )
    with (
        patch(
            "app.routers.lesson_classroom.get_generation_state",
            new=AsyncMock(
                return_value=ExerciseGenerationState(generation_status="generating")
            ),
        ),
        patch(
            "app.routers.lesson_classroom.GenerationLease.acquire",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = await client.get(f"/api/lessons/{lesson.id}/classroom/deck", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generating"
    assert data["mode"] == "reading"
    assert data["fallback_deck"]["lesson_id"] == lesson.id
    assert data["fallback_deck"]["beats"][0]["id"] == "intro"
    assert data["pack"] is None


@pytest.mark.asyncio
async def test_classroom_pack_cache_hit_and_content_hash_invalidation(
    client, test_user, db_session
):
    from tests.test_lessons_router import _create_lesson_with_plan

    user, headers = test_user
    content = {
        "explanation": {
            "text": "We study the past.",
            "key_points": ["Regular -ar verbs"],
            "examples": [],
        }
    }
    lesson = await _create_lesson_with_plan(
        db_session,
        user.id,
        title="Unit one",
        content=content,
    )
    content_hash = lesson_content_hash(content)
    pack = normalize_classroom_pack(
        _sample_llm_pack(),
        lesson=lesson,
        target_language="en-US",
        content_hash=content_hash,
    )
    await save_classroom_pack(db_session, pack)

    response = await client.get(f"/api/lessons/{lesson.id}/classroom/deck", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["mode"] == "lecture"
    assert data["pack"]["segments"][0]["speech_text"] != data["pack"]["slides"][0]["title"]
    assert data["pack"]["content_hash"] == content_hash

    pack_response = await client.get(
        f"/api/lessons/{lesson.id}/classroom/pack", headers=headers
    )
    assert pack_response.status_code == 200
    assert pack_response.json()["status"] == "ready"

    lesson.content = {
        "explanation": {"text": "Changed content.", "key_points": [], "examples": []}
    }
    await db_session.commit()
    await db_session.refresh(lesson)
    stored = await get_stored_pack(db_session, lesson, target_language="en-US")
    assert stored is None


@pytest.mark.asyncio
async def test_classroom_generate_failure_still_serves_fallback(
    client, test_user, db_session
):
    from app.schemas.exercise_generation import ExerciseGenerationState
    from tests.test_lessons_router import _create_lesson_with_plan

    user, headers = test_user
    lesson = await _create_lesson_with_plan(
        db_session,
        user.id,
        content={"explanation": {"text": "Hi.", "key_points": [], "examples": []}},
    )
    with (
        patch(
            "app.routers.lesson_classroom.get_generation_state",
            new=AsyncMock(
                return_value=ExerciseGenerationState(
                    generation_status="failed", generation_error="generation_failed"
                )
            ),
        ),
        patch(
            "app.routers.lesson_classroom.GenerationLease.acquire",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = await client.get(
            f"/api/lessons/{lesson.id}/classroom/deck", headers=headers
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "fallback"
    assert data["mode"] == "reading"
    assert data["fallback_deck"] is not None
    assert data["fallback_deck"]["beats"]


@pytest.mark.asyncio
async def test_classroom_pack_other_user_forbidden(client, test_user, db_session):
    from app.core.security import hash_password
    from app.models.user import User
    from tests.test_lessons_router import _create_lesson_with_plan

    owner = User(
        username="classroomowner2",
        email="classroomowner2@example.com",
        display_name="Owner",
        hashed_password=hash_password("ownerpass"),
        role="user",
        native_language="en",
        is_active=True,
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)
    lesson = await _create_lesson_with_plan(
        db_session,
        owner.id,
        content={"explanation": {"text": "Hola.", "key_points": [], "examples": []}},
    )
    _, headers = test_user
    response = await client.get(f"/api/lessons/{lesson.id}/classroom/pack", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_classroom_clarify_unknown_beat(client, test_user, db_session):
    from tests.test_lessons_router import _create_lesson_with_plan

    user, headers = test_user
    lesson = await _create_lesson_with_plan(
        db_session,
        user.id,
        content={"explanation": {"text": "Hi.", "key_points": [], "examples": []}},
    )
    response = await client.post(
        f"/api/lessons/{lesson.id}/classroom/clarify",
        headers=headers,
        json={"beat_id": "nope", "action": "rephrase"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_classroom_clarify_uses_plan_language_and_returns_annotations(
    client, test_user, db_session
):
    from app.models.lesson import Lesson
    from app.services.language_helpers import get_language_name
    from tests.conftest import make_study_plan

    user, headers = test_user
    plan = await make_study_plan(
        db_session,
        user_id=user.id,
        target_language="es-ES",
        cefr_level="A2",
        goals=["grammar"],
        duration_weeks=4,
        days_per_week=4,
        current_unit="",
        generated_plan={},
        is_active=True,
    )
    lesson = Lesson(
        study_plan_id=plan.id,
        title="Pasado",
        lesson_type="grammar",
        cefr_level="A2",
        week_number=1,
        day_number=1,
        content={
            "explanation": {
                "text": "Usamos el pretérito.",
                "key_points": [],
                "examples": [],
            }
        },
    )
    db_session.add(lesson)
    await db_session.commit()
    await db_session.refresh(lesson)

    llm_result = ClassroomClarifyLLMResult(
        spoken_text="Usamos el pasado simple.",
        display_text="Usamos el pasado simple.",
        annotations=[{"type": "margin_note", "payload": "pasado simple = pretérito"}],
    )
    with patch(
        "app.routers.lesson_classroom.llm_adapter.structured_output",
        new=AsyncMock(return_value=llm_result),
    ) as mock_llm:
        response = await client.post(
            f"/api/lessons/{lesson.id}/classroom/clarify",
            headers=headers,
            json={
                "beat_id": "explanation-0",
                "action": "rephrase",
                "ui_locale": "en",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["spoken_text"] == "Usamos el pasado simple."
    assert body["annotations"][0]["beat_id"] == "explanation-0"
    assert body["annotations"][0]["type"] == "margin_note"
    prompt = mock_llm.await_args.args[0][0]["content"]
    assert get_language_name("es-ES") in prompt
    assert "Usamos el pretérito." in prompt


@pytest.mark.asyncio
async def test_classroom_clarify_rejects_annotate_action(client, test_user, db_session):
    from tests.test_lessons_router import _create_lesson_with_plan

    user, headers = test_user
    lesson = await _create_lesson_with_plan(
        db_session,
        user.id,
        content={"explanation": {"text": "Hi.", "key_points": [], "examples": []}},
    )
    response = await client.post(
        f"/api/lessons/{lesson.id}/classroom/clarify",
        headers=headers,
        json={"beat_id": "explanation-0", "action": "annotate"},
    )
    assert response.status_code == 422
