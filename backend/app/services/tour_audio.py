"""Persistent, shared cache for localized dashboard tour narration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.services.tts_service import KokoroTTSService, OpenAITTSService

OPENAI_VOICES = frozenset(
    {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}
)


def _lock_exclusive(lock: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        lock.seek(0)
        if lock.read(1) == b"":
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(lock: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(lock, fcntl.LOCK_UN)


async def get_tour_audio(
    service: KokoroTTSService | OpenAITTSService,
    *,
    locale: str,
    text: str,
    voice: str | None,
) -> Path:
    is_openai = isinstance(service, OpenAITTSService)
    effective_voice = (voice or service.voice) if is_openai else service.voice
    if is_openai:
        key = service.get_cache_key(text, effective_voice, locale)
    else:
        identity = {
            "text": text,
            "locale": locale,
            "provider": "local",
            "model": "kokoro",
            "voice": effective_voice,
            "speed": 1.0,
            "format": "mp3",
        }
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    directory = Path(settings.AUDIO_STORAGE_PATH) / "tour" / locale
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.mp3"

    def cached() -> bool:
        return path.is_file() and path.stat().st_size > 0

    if cached():
        return path

    async with asyncio.timeout(60):
        with (directory / f"{key}.lock").open("a+b") as lock:
            while True:
                try:
                    _lock_exclusive(lock)
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            try:
                if cached():
                    return path
                audio = await service.synthesize(text, effective_voice, language=locale)
                if not audio:
                    raise ValueError("Empty tour narration")
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=directory, suffix=".tmp", delete=False
                    ) as out:
                        temporary = Path(out.name)
                        out.write(audio)
                    os.replace(temporary, path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            finally:
                _unlock(lock)
    return path
