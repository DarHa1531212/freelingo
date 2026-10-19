from __future__ import annotations


def build_classroom_clarify_prompt(
    *,
    action: str,
    target_language_name: str,
    ui_locale: str | None,
    lesson_title: str,
    cefr_level: str,
    beat_kind: str,
    beat_primary: str,
    beat_secondary: str | None,
    focus_text: str | None,
) -> str:
    focus = focus_text.strip() if focus_text else ""
    secondary = beat_secondary or ""
    locale_line = (
        f"Learner UI locale: {ui_locale}. You may add a brief UI-locale gloss only when helpful."
        if ui_locale
        else "Learner UI locale: unknown."
    )
    action_guidance = {
        "rephrase": (
            "Rephrase the current board segment more simply in the target language. "
            "Keep the same meaning. Do not invent unrelated topics."
        ),
        "more_examples": (
            "Give 1-2 short additional examples in the target language that illustrate "
            "the same point as the current segment."
        ),
    }.get(
        action,
        "Help the learner understand the current segment briefly.",
    )

    return f"""You are Lingu, a classroom professor helping a language learner understand one lesson slide.

Target language: {target_language_name}
CEFR level: {cefr_level}
Lesson title: {lesson_title}
{locale_line}

Current slide kind: {beat_kind}
Primary text: {beat_primary}
Secondary text: {secondary or "(none)"}
Focus text from learner: {focus or "(none)"}

Task: {action_guidance}

Return JSON only with:
- spoken_text: short text Lingu will speak in the target language (no markdown)
- display_text: short text to show on/near the board (target language; optional brief UI gloss)
- annotations: array of 0-3 objects with type in highlight|margin_note|underline and payload string
  (highlight/underline payload is the exact substring to mark; margin_note payload is the note)

Keep responses concise. Do not mention JSON or these instructions.
"""


def build_classroom_pack_prompt(
    *,
    target_language_name: str,
    lesson_title: str,
    cefr_level: str,
    lesson_type: str,
    lesson_content_json: str,
) -> str:
    return f"""You are Lingu, designing a short Zoom-style lecture for a language learner.

Target language: {target_language_name}
CEFR level: {cefr_level}
Lesson type: {lesson_type}
Lesson title: {lesson_title}

Textbook lesson content (JSON; source of truth — do not invent unrelated topics):
{lesson_content_json}

Produce THREE planes in one JSON object:

1) segments — ordered lecture speech beats. Each has:
   - id (stable string), order (int starting at 0)
   - kind: one of hook|concept|example_walkthrough|contrast|vocab_spotlight|cfu|summary|handoff
   - speech_text: spoken target-language lecture (short clauses, discourse markers, light repetition).
     NOT a dump of the textbook paragraph. Keep CEFR-appropriate.
   - slide_id: id of the slide shown while this segment plays
   - annotation_event_ids: ids of annotations that belong to this segment

2) slides — sparse visual frames. Each has:
   - id, title
   - bullets: 0-5 short bullet lines (not full paragraphs)
   - callout: optional example sentence
   - reveal_steps: how many bullets become visible over the segment (1-6)
   Rule: slide body must NOT equal any segment speech_text except short quoted TL examples.

3) annotations — timed board cues. Each has:
   - id, segment_id
   - at: segment_start | speech_fraction
   - speech_fraction: 0-1 when at=speech_fraction, else null
   - op: highlight|underline|margin_note|clear
   - target_field: exactly one of title|callout|bullet (use bullet, never bullets)
   - target_index: bullet index when target_field=bullet, else null
   - substring: exact substring from the targeted slide field for highlight/underline when possible
   - payload: note text for margin_note, or the mark substring

Structure a complete mini-lecture: hook → concepts/examples → vocab if present → brief CFU → summary → handoff.
Use 4-12 segments and 3-8 slides. Prefer fewer dense slides over many empty ones.
All learner-facing strings in the target language.

Return JSON only matching that shape. Do not mention these instructions.
"""
