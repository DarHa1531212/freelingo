from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_redis
from app.core.limiter import limiter
from app.models.study_plan import StudyPlan
from app.models.user import User
from app.routers.lessons import _get_lesson_for_user
from app.schemas.classroom import (
    ClassroomAnnotationOp,
    ClassroomClarifyLLMResult,
    ClassroomClarifyRequest,
    ClassroomClarifyResponse,
    ClassroomGenerateResponse,
    ClassroomPackStatusResponse,
    ClassroomSessionResponse,
)
from app.services.exercise_generation import GenerationLease, get_generation_state
from app.services.language_helpers import get_language_name
from app.services.lesson_classroom import (
    build_classroom_deck,
    find_beat,
    find_segment,
    find_slide,
    generate_and_store_classroom_pack,
    get_stored_pack,
)
from app.services.llm_adapter import (
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    llm_adapter,
)
from app.services.prompts.classroom import build_classroom_clarify_prompt
from app.utils.db import db_session
from app.utils.redis import redis_client as _redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lessons", tags=["classroom"])


def _lock_key(lesson_id: int) -> str:
    return f"classroom:pack:{lesson_id}"


async def _background_generate_pack(
    lesson_id: int,
    target_language: str,
    lease: GenerationLease,
) -> None:
    async with _redis_client() as redis_conn:

        async def work(deadline: float) -> None:
            async with db_session() as db:
                await lease.ensure_owner(redis_conn)
                await generate_and_store_classroom_pack(
                    db,
                    lesson_id,
                    target_language=target_language,
                )

        await lease.run(redis_conn, work)


async def _maybe_start_generation(
    *,
    lesson_id: int,
    target_language: str,
    redis: Redis,
    background_tasks: BackgroundTasks,
) -> bool:
    generation = await get_generation_state(redis, _lock_key(lesson_id))
    if generation.generation_status == "generating":
        return True
    lease = await GenerationLease.acquire(redis, _lock_key(lesson_id))
    if lease is None:
        return True
    background_tasks.add_task(
        _background_generate_pack,
        lesson_id,
        target_language,
        lease,
    )
    return True


@router.get("/{lesson_id}/classroom/deck", response_model=ClassroomSessionResponse)
@limiter.limit("60/minute")
async def get_classroom_deck(
    request: Request,
    lesson_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ClassroomSessionResponse:
    lesson = await _get_lesson_for_user(lesson_id, current_user.id, db)
    plan = await db.get(StudyPlan, lesson.study_plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    fallback = build_classroom_deck(lesson, target_language=plan.target_language)
    pack = await get_stored_pack(db, lesson, target_language=plan.target_language)
    if pack is not None:
        return ClassroomSessionResponse(
            status="ready",
            mode="lecture",
            pack=pack,
            fallback_deck=fallback,
            preparing=False,
        )

    generation = await get_generation_state(redis, _lock_key(lesson_id))
    preparing = await _maybe_start_generation(
        lesson_id=lesson.id,
        target_language=plan.target_language,
        redis=redis,
        background_tasks=background_tasks,
    )
    if generation.generation_status == "failed":
        return ClassroomSessionResponse(
            status="fallback",
            mode="reading",
            pack=None,
            fallback_deck=fallback,
            preparing=preparing,
        )
    return ClassroomSessionResponse(
        status="generating",
        mode="reading",
        pack=None,
        fallback_deck=fallback,
        preparing=True,
    )


@router.get("/{lesson_id}/classroom/pack", response_model=ClassroomPackStatusResponse)
@limiter.limit("60/minute")
async def get_classroom_pack(
    request: Request,
    lesson_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ClassroomPackStatusResponse:
    lesson = await _get_lesson_for_user(lesson_id, current_user.id, db)
    plan = await db.get(StudyPlan, lesson.study_plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    pack = await get_stored_pack(db, lesson, target_language=plan.target_language)
    if pack is not None:
        return ClassroomPackStatusResponse(status="ready", pack=pack)

    generation = await get_generation_state(redis, _lock_key(lesson_id))
    if generation.generation_status == "generating":
        return ClassroomPackStatusResponse(status="generating", pack=None)
    if generation.generation_status == "failed":
        return ClassroomPackStatusResponse(status="failed", pack=None)
    return ClassroomPackStatusResponse(status="missing", pack=None)


@router.post(
    "/{lesson_id}/classroom/pack/generate",
    response_model=ClassroomGenerateResponse,
)
@limiter.limit("10/minute")
async def generate_classroom_pack_endpoint(
    request: Request,
    lesson_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ClassroomGenerateResponse:
    lesson = await _get_lesson_for_user(lesson_id, current_user.id, db)
    plan = await db.get(StudyPlan, lesson.study_plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    pack = await get_stored_pack(db, lesson, target_language=plan.target_language)
    if pack is not None:
        return ClassroomGenerateResponse(status="ready", pack=pack)

    await _maybe_start_generation(
        lesson_id=lesson.id,
        target_language=plan.target_language,
        redis=redis,
        background_tasks=background_tasks,
    )
    return ClassroomGenerateResponse(status="generating", pack=None)


@router.post("/{lesson_id}/classroom/clarify", response_model=ClassroomClarifyResponse)
@limiter.limit("20/minute")
async def clarify_classroom_beat(
    request: Request,
    lesson_id: int,
    body: ClassroomClarifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClassroomClarifyResponse:
    lesson = await _get_lesson_for_user(lesson_id, current_user.id, db)
    plan = await db.get(StudyPlan, lesson.study_plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    pack = await get_stored_pack(db, lesson, target_language=plan.target_language)
    segment_id = body.segment_id or body.beat_id
    if pack is not None:
        segment = find_segment(pack, segment_id)
        if segment is not None:
            slide = find_slide(pack, segment.slide_id)
            beat_kind = segment.kind
            beat_primary = segment.speech_text
            beat_secondary = None
            if slide is not None:
                joined = " · ".join(
                    part for part in [slide.title, *slide.bullets, slide.callout or ""] if part
                )
                beat_secondary = joined or None
            annotation_beat_id = segment.id
        else:
            deck = build_classroom_deck(lesson, target_language=plan.target_language)
            beat = find_beat(deck, body.beat_id)
            if beat is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown beat_id"
                )
            beat_kind = beat.kind
            beat_primary = beat.primary_text
            beat_secondary = beat.secondary_text
            annotation_beat_id = beat.id
    else:
        deck = build_classroom_deck(lesson, target_language=plan.target_language)
        beat = find_beat(deck, body.beat_id)
        if beat is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown beat_id")
        beat_kind = beat.kind
        beat_primary = beat.primary_text
        beat_secondary = beat.secondary_text
        annotation_beat_id = beat.id

    prompt = build_classroom_clarify_prompt(
        action=body.action,
        target_language_name=get_language_name(plan.target_language),
        ui_locale=body.ui_locale,
        lesson_title=lesson.title,
        cefr_level=lesson.cefr_level,
        beat_kind=beat_kind,
        beat_primary=beat_primary,
        beat_secondary=beat_secondary,
        focus_text=body.focus_text,
    )

    try:
        result = await llm_adapter.structured_output(
            [{"role": "user", "content": prompt}],
            ClassroomClarifyLLMResult,
        )
    except (LLMError, LLMTimeoutError, LLMUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Classroom help is unavailable right now",
        )

    data = (
        result
        if isinstance(result, ClassroomClarifyLLMResult)
        else ClassroomClarifyLLMResult.model_validate(result)
    )
    annotations = [
        ClassroomAnnotationOp(
            beat_id=annotation_beat_id,
            type=item.type,
            payload=item.payload.strip(),
        )
        for item in data.annotations
        if item.payload.strip()
    ][:3]

    return ClassroomClarifyResponse(
        spoken_text=data.spoken_text.strip(),
        display_text=data.display_text.strip(),
        annotations=annotations,
    )
