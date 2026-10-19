'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import { AudioPlayer } from '@/components/ui/AudioPlayer'
import { apiFetch } from '@/lib/api'
import { GrammarTablesPanel } from './GrammarTablesPanel'
import { HelpPanel } from './HelpPanel'
import { WhiteboardBoard } from './WhiteboardBoard'
import type {
  AnnotationEvent,
  ClassroomAnnotationOp,
  ClassroomClarifyAction,
  ClassroomClarifyResponse,
  ClassroomDeck,
  ClassroomGrammarTable,
  ClassroomPack,
  LectureSegment,
  SlideFrame,
} from './types'

const CLASSROOM_TTS_TIMEOUT_MS = 45_000

function eventToOps(
  event: AnnotationEvent,
  segmentId: string
): ClassroomAnnotationOp[] {
  if (event.op === 'clear') return []
  if (event.op === 'margin_note') {
    return [
      {
        beat_id: segmentId,
        type: 'margin_note',
        payload: event.payload,
        target_field: event.target_field,
        target_index: event.target_index,
      },
    ]
  }
  const payload = event.substring || event.payload
  if (!payload) return []
  return [
    {
      beat_id: segmentId,
      type: event.op,
      payload,
      target_field: event.target_field,
      target_index: event.target_index,
    },
  ]
}

function visibleBulletCount(
  slide: SlideFrame,
  fraction: number,
  playing: boolean
): number {
  if (!playing && fraction <= 0) return Math.min(1, slide.bullets.length) || 0
  const steps = Math.max(1, Math.min(slide.reveal_steps, slide.bullets.length || 1))
  const revealed = Math.min(
    slide.bullets.length,
    Math.max(1, Math.ceil(fraction * steps))
  )
  return slide.bullets.length === 0 ? 0 : revealed
}

export function ClassroomPresenter({
  pack,
  deck,
  preparing = false,
  grammarTables = [],
}: {
  pack?: ClassroomPack | null
  deck?: ClassroomDeck | null
  preparing?: boolean
  grammarTables?: ClassroomGrammarTable[]
}) {
  const t = useTranslations('classroom')
  const locale = useLocale()
  const lectureMode = Boolean(pack?.segments.length)
  const lessonId = pack?.lesson_id ?? deck?.lesson_id ?? 0
  const studyPlanId = pack?.study_plan_id ?? deck?.study_plan_id ?? 0
  const targetLanguage = pack?.target_language ?? deck?.target_language ?? 'en-GB'
  const title = pack?.title ?? deck?.title ?? ''
  const cefrLevel = pack?.cefr_level ?? deck?.cefr_level ?? ''

  const [index, setIndex] = useState(0)
  const [annotations, setAnnotations] = useState<ClassroomAnnotationOp[]>([])
  const [helpText, setHelpText] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [autoPlaying, setAutoPlaying] = useState(false)
  const [playerEpoch, setPlayerEpoch] = useState(0)
  const [speechFraction, setSpeechFraction] = useState(0)
  const durationRef = useRef(0)
  const startedAtRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)
  const appliedFractionIdsRef = useRef<Set<string>>(new Set())
  const prefetchRef = useRef<Map<string, string>>(new Map())

  const segments = pack?.segments ?? []
  const beats = deck?.beats ?? []
  const total = lectureMode ? segments.length : beats.length
  const segment: LectureSegment | null = lectureMode
    ? (segments[index] ?? null)
    : null
  const beat = !lectureMode ? (beats[index] ?? null) : null
  const slide =
    lectureMode && segment
      ? (pack?.slides.find((item) => item.id === segment.slide_id) ?? null)
      : null

  const narrationText = lectureMode
    ? (segment?.speech_text ?? '')
    : (beat?.narration_text ?? '')

  const isFirst = index === 0
  const isLast = total > 0 && index >= total - 1
  const showHelp = lectureMode
    ? Boolean(segment && segment.kind !== 'handoff')
    : Boolean(beat && beat.kind !== 'closing')

  function stopTicker() {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    startedAtRef.current = null
  }

  function applySegmentStartAnnotations(nextSegment: LectureSegment) {
    if (!pack) return
    const events = pack.annotations.filter(
      (event) =>
        event.segment_id === nextSegment.id &&
        (nextSegment.annotation_event_ids.includes(event.id) ||
          event.at === 'segment_start')
    )
    const startOps = events
      .filter((event) => event.at === 'segment_start')
      .flatMap((event) => eventToOps(event, nextSegment.id))
    setAnnotations(startOps)
    appliedFractionIdsRef.current = new Set(
      startOps.map((op) => `${op.type}:${op.payload}`)
    )
  }

  function goToIndex(nextIndex: number, { keepPlaying }: { keepPlaying: boolean }) {
    const clamped = Math.max(0, Math.min(total - 1, nextIndex))
    setIndex(clamped)
    setHelpText(null)
    setError('')
    setSpeechFraction(0)
    durationRef.current = 0
    stopTicker()
    setPlayerEpoch((value) => value + 1)
    if (!keepPlaying) {
      setAutoPlaying(false)
      setAnnotations([])
      return
    }
    if (lectureMode) {
      const next = segments[clamped]
      if (next) applySegmentStartAnnotations(next)
      else setAnnotations([])
    } else {
      setAnnotations([])
    }
  }

  useEffect(() => {
    setHelpText(null)
    setSpeechFraction(0)
    appliedFractionIdsRef.current = new Set()
  }, [lectureMode, segment?.id, beat?.id])

  useEffect(() => {
    return () => {
      stopTicker()
      for (const url of prefetchRef.current.values()) {
        URL.revokeObjectURL(url)
      }
      prefetchRef.current.clear()
    }
  }, [])

  useEffect(() => {
    if (!lectureMode || !autoPlaying || !pack) return
    const next = segments[index + 1]
    if (!next?.speech_text || prefetchRef.current.has(next.speech_text)) return
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch('/api/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: next.speech_text,
            study_plan_id: studyPlanId,
          }),
        })
        if (!res.ok || cancelled) return
        const blob = await res.blob()
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        const previous = prefetchRef.current.get(next.speech_text)
        if (previous) URL.revokeObjectURL(previous)
        prefetchRef.current.set(next.speech_text, url)
      } catch {
        return
      }
    })()
    return () => {
      cancelled = true
    }
  }, [autoPlaying, index, lectureMode, pack, segments, studyPlanId])

  const progressLabel = useMemo(
    () => t('progress', { current: total === 0 ? 0 : index + 1, total }),
    [index, t, total]
  )

  const kindLabel = lectureMode
    ? t(`segmentKinds.${segment?.kind ?? 'concept'}`)
    : t(`kinds.${beat?.kind ?? 'explanation'}`)

  const boardAnnotations = annotations.filter((item) =>
    lectureMode ? item.beat_id === segment?.id : item.beat_id === beat?.id
  )

  async function clarify(action: ClassroomClarifyAction) {
    if (busy) return
    const beatId = lectureMode ? segment?.id : beat?.id
    if (!beatId) return
    setBusy(true)
    setError('')
    try {
      const res = await apiFetch(`/api/lessons/${lessonId}/classroom/clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          beat_id: beatId,
          segment_id: lectureMode ? beatId : undefined,
          action,
          ui_locale: locale,
        }),
      })
      if (!res.ok) {
        throw new Error('clarify_failed')
      }
      const data = (await res.json()) as ClassroomClarifyResponse
      setHelpText(data.display_text || data.spoken_text)
      if (data.spoken_text) {
        setAutoPlaying(false)
        setPlayerEpoch((value) => value + 1)
      }
      if (data.annotations?.length) {
        setAnnotations((previous) => [...previous, ...data.annotations])
      }
    } catch {
      setError(t('clarifyError'))
    } finally {
      setBusy(false)
    }
  }

  function repeat() {
    setAutoPlaying(false)
    setPlayerEpoch((value) => value + 1)
    setTimeout(() => {
      setAutoPlaying(true)
      setPlayerEpoch((value) => value + 1)
    }, 0)
  }

  function playLecture() {
    if (lectureMode && segment) applySegmentStartAnnotations(segment)
    setSpeechFraction(0)
    setAutoPlaying(true)
    setPlayerEpoch((value) => value + 1)
  }

  function pauseLecture() {
    setAutoPlaying(false)
    stopTicker()
    setPlayerEpoch((value) => value + 1)
  }

  function onDuration(seconds: number) {
    durationRef.current = seconds
    startedAtRef.current = performance.now()
    stopTicker()
    const tick = () => {
      if (!startedAtRef.current || durationRef.current <= 0) return
      const fraction = Math.min(
        1,
        (performance.now() - startedAtRef.current) / (durationRef.current * 1000)
      )
      setSpeechFraction(fraction)
      if (lectureMode && segment && pack) {
        for (const event of pack.annotations) {
          if (
            event.segment_id !== segment.id ||
            event.at !== 'speech_fraction' ||
            event.speech_fraction == null
          ) {
            continue
          }
          if (fraction + 0.02 < event.speech_fraction) continue
          if (appliedFractionIdsRef.current.has(event.id)) continue
          appliedFractionIdsRef.current.add(event.id)
          if (event.op === 'clear') {
            setAnnotations([])
          } else {
            setAnnotations((previous) => [
              ...previous,
              ...eventToOps(event, segment.id),
            ])
          }
        }
      }
      if (fraction < 1) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }
    rafRef.current = requestAnimationFrame(tick)
  }

  function onEnded() {
    stopTicker()
    setSpeechFraction(1)
    if (!autoPlaying) return
    if (isLast) {
      setAutoPlaying(false)
      return
    }
    goToIndex(index + 1, { keepPlaying: true })
  }

  if (total === 0) {
    return (
      <div className="border-fl-border bg-fl-surface border px-6 py-10 text-center">
        <p className="text-fl-muted-3 font-sans text-sm">{t('emptyDeck')}</p>
        <Link
          href={`/lesson/${lessonId}?focus=exercises`}
          className="text-fl-fg mt-4 inline-block font-sans text-sm underline"
        >
          {t('toExercises')}
        </Link>
      </div>
    )
  }

  const prefetchedUrl =
    narrationText && prefetchRef.current.has(narrationText)
      ? prefetchRef.current.get(narrationText)
      : undefined

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <div className="border-fl-border bg-fl-surface flex flex-wrap items-center justify-between gap-3 border px-6 py-4">
        <div>
          <p className="text-fl-label text-fl-muted-2 font-mono tracking-widest uppercase">
            {lectureMode ? t('lectureLabel') : t('label')}
          </p>
          <p className="text-fl-fg font-mono text-base font-bold tracking-wide">
            {title}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-fl-hint text-fl-muted-2 border-fl-border border px-2 py-1 font-mono tracking-widest uppercase">
            {cefrLevel}
          </span>
          <span className="text-fl-hint text-fl-muted-2 font-mono tracking-widest uppercase">
            {progressLabel}
          </span>
          <Link
            href={`/lesson/${lessonId}`}
            className="text-fl-muted-3 hover:text-fl-fg font-mono text-lg leading-none transition-colors"
            aria-label={t('exit')}
          >
            ✕
          </Link>
        </div>
      </div>

      {preparing && (
        <p className="text-fl-muted-3 border-fl-border bg-fl-surface border px-4 py-2 font-sans text-sm">
          {t('preparing')}
        </p>
      )}

      <WhiteboardBoard
        beat={beat}
        slide={slide}
        visibleBullets={
          slide
            ? visibleBulletCount(slide, speechFraction, autoPlaying)
            : undefined
        }
        kindLabel={kindLabel}
        annotations={boardAnnotations}
        helpText={helpText}
        targetLanguage={targetLanguage}
      />

      <GrammarTablesPanel
        tables={grammarTables}
        targetLanguage={targetLanguage}
      />

      <div className="border-fl-border bg-fl-surface flex flex-wrap items-center gap-3 border px-4 py-3">
        {lectureMode ? (
          <>
            {autoPlaying ? (
              <button
                type="button"
                onClick={pauseLecture}
                className="border-fl-border text-fl-fg hover:bg-fl-surface-2 border px-3 py-2 font-mono text-sm tracking-widest uppercase"
              >
                {t('pause')}
              </button>
            ) : (
              <button
                type="button"
                onClick={playLecture}
                className="bg-fl-fg text-fl-bg hover:bg-fl-fg/90 px-3 py-2 font-mono text-sm font-bold tracking-widest uppercase"
              >
                {t('playLecture')}
              </button>
            )}
          </>
        ) : null}
        <AudioPlayer
          key={`${lectureMode ? segment?.id : beat?.id}-${playerEpoch}`}
          text={narrationText}
          studyPlanId={studyPlanId}
          size="md"
          timeoutMs={CLASSROOM_TTS_TIMEOUT_MS}
          autoPlay={autoPlaying}
          audioUrl={prefetchedUrl}
          audioMethod={prefetchedUrl ? 'GET' : 'POST'}
          onEnded={onEnded}
          onDuration={onDuration}
        />
        <p className="text-fl-muted-3 font-sans text-sm">
          {lectureMode ? t('lectureHint') : t('narrationHint')}
        </p>
      </div>

      {showHelp && (
        <HelpPanel busy={busy} onRepeat={repeat} onClarify={clarify} />
      )}

      {error && (
        <p className="text-fl-danger font-sans text-sm" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          disabled={isFirst}
          onClick={() => goToIndex(index - 1, { keepPlaying: false })}
          className="border-fl-border text-fl-fg hover:bg-fl-surface-2 disabled:text-fl-muted-4 border px-4 py-2 font-sans text-sm transition-colors disabled:cursor-not-allowed"
        >
          {t('previous')}
        </button>
        {isLast ? (
          <Link
            href={`/lesson/${lessonId}?focus=exercises`}
            className="bg-fl-fg text-fl-bg hover:bg-fl-fg/90 px-4 py-2 font-mono text-sm font-bold tracking-widest uppercase transition-colors"
          >
            {t('toExercises')}
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => goToIndex(index + 1, { keepPlaying: autoPlaying })}
            className="bg-fl-fg text-fl-bg hover:bg-fl-fg/90 px-4 py-2 font-mono text-sm font-bold tracking-widest uppercase transition-colors"
          >
            {t('next')}
          </button>
        )}
      </div>
    </div>
  )
}
