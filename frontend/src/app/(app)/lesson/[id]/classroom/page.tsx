'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ClassroomPresenter } from '@/components/lesson/classroom/ClassroomPresenter'
import type {
  ClassroomPack,
  ClassroomPackStatusResponse,
  ClassroomSessionResponse,
} from '@/components/lesson/classroom/types'
import { PageLoading } from '@/components/ui/page-loading'
import { apiFetch } from '@/lib/api'

const POLL_MS = 2500
const CLASSROOM_CLIENT_BUILD = 'lecture-redesign-2026-10-19a'

export default function LessonClassroomPage() {
  const params = useParams<{ id: string }>()
  const id = Number(params.id)
  const t = useTranslations('classroom')
  const [session, setSession] = useState<ClassroomSessionResponse | null>(null)
  const [pack, setPack] = useState<ClassroomPack | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    console.info('[classroom]', CLASSROOM_CLIENT_BUILD, 'page mount', { lessonId: id })
  }, [id])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const loadSession = useCallback(async () => {
    if (!Number.isFinite(id) || id <= 0) {
      setError(true)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(false)
    try {
      const res = await apiFetch(`/api/lessons/${id}/classroom/deck`)
      if (!res.ok) {
        throw new Error('deck_failed')
      }
      const data = (await res.json()) as ClassroomSessionResponse
      console.info('[classroom]', CLASSROOM_CLIENT_BUILD, 'session', {
        status: data.status,
        mode: data.mode,
        preparing: data.preparing,
        hasPack: Boolean(data.pack),
        segments: data.pack?.segments.length ?? 0,
        fallbackBeats: data.fallback_deck?.beats.length ?? 0,
      })
      setSession(data)
      setPack(data.pack)
      if (data.status === 'ready' && data.pack) {
        stopPolling()
      }
    } catch {
      setSession(null)
      setPack(null)
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [id, stopPolling])

  useEffect(() => {
    void loadSession()
    return stopPolling
  }, [loadSession, stopPolling])

  useEffect(() => {
    if (!session || session.status === 'ready' || pack) {
      stopPolling()
      return
    }
    if (pollRef.current) return
    pollRef.current = setInterval(() => {
      void (async () => {
        try {
          const res = await apiFetch(`/api/lessons/${id}/classroom/pack`)
          if (!res.ok) return
          const data = (await res.json()) as ClassroomPackStatusResponse
          if (data.status === 'ready' && data.pack) {
            setPack(data.pack)
            setSession((previous) =>
              previous
                ? {
                    ...previous,
                    status: 'ready',
                    mode: 'lecture',
                    pack: data.pack,
                    preparing: false,
                  }
                : previous
            )
            stopPolling()
          }
        } catch {
          return
        }
      })()
    }, POLL_MS)
    return stopPolling
  }, [id, pack, session, stopPolling])

  if (loading) return <PageLoading />

  if (error || !session || (!session.pack && !session.fallback_deck)) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        <div className="border-fl-border bg-fl-surface border px-6 py-10 text-center">
          <p className="text-fl-muted-3 font-sans text-sm">{t('loadError')}</p>
          <div className="mt-4 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={() => void loadSession()}
              className="border-fl-border text-fl-fg hover:bg-fl-surface-2 border px-4 py-2 font-sans text-sm"
            >
              {t('retry')}
            </button>
            <Link
              href={`/lesson/${id}`}
              className="text-fl-fg font-sans text-sm underline"
            >
              {t('backToLesson')}
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const activePack = pack ?? session.pack
  const preparing = Boolean(session.preparing && !activePack)

  return (
    <ClassroomPresenter
      pack={activePack}
      deck={activePack ? null : session.fallback_deck}
      preparing={preparing}
    />
  )
}
