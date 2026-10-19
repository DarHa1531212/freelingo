import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  push: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
  useParams: () => ({ id: '7' }),
}))

vi.mock('next-intl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-intl')>()
  const { default: messages } = await import('../../../messages/en.json')
  const classroom = actual.createTranslator({
    locale: 'en',
    messages,
    namespace: 'classroom',
  })
  return {
    useLocale: () => 'en',
    useTranslations: (namespace: string) => {
      if (namespace === 'classroom') return classroom
      return (key: string) => `${namespace}.${key}`
    },
  }
})

vi.mock('@/lib/api', () => ({ apiFetch: mocks.apiFetch }))
vi.mock('@/components/ui/AudioPlayer', () => ({
  AudioPlayer: (props: {
    text: string
    studyPlanId?: number
    autoPlay?: boolean
    onEnded?: () => void
  }) => (
    <div
      data-testid="audio-player"
      data-text={props.text}
      data-plan={props.studyPlanId}
      data-autoplay={props.autoPlay ? 'true' : 'false'}
    >
      <button type="button" onClick={() => props.onEnded?.()}>
        end-audio
      </button>
    </div>
  ),
}))
vi.mock('@/components/ui/page-loading', () => ({
  PageLoading: () => <div data-testid="loading" />,
}))

import { LessonClassroomEntry } from '@/components/lesson/LessonClassroomEntry'
import { ClassroomPresenter } from '@/components/lesson/classroom/ClassroomPresenter'
import type {
  ClassroomDeck,
  ClassroomPack,
  ClassroomSessionResponse,
} from '@/components/lesson/classroom/types'
import LessonClassroomPage from '@/app/(app)/lesson/[id]/classroom/page'

function deck(overrides: Partial<ClassroomDeck> = {}): ClassroomDeck {
  return {
    lesson_id: 7,
    study_plan_id: 3,
    target_language: 'es-ES',
    title: 'Pasado simple',
    cefr_level: 'A2',
    lesson_type: 'grammar',
    beats: [
      {
        id: 'intro',
        kind: 'intro',
        title: 'grammar',
        primary_text: 'Pasado simple',
        secondary_text: null,
        narration_text: 'Pasado simple',
      },
      {
        id: 'explanation-0',
        kind: 'explanation',
        title: null,
        primary_text: 'Usamos el pretérito.',
        secondary_text: null,
        narration_text: 'Usamos el pretérito.',
      },
      {
        id: 'closing',
        kind: 'closing',
        title: null,
        primary_text: 'Ready for practice',
        secondary_text: null,
        narration_text: 'Ready for practice',
      },
    ],
    ...overrides,
  }
}

function pack(overrides: Partial<ClassroomPack> = {}): ClassroomPack {
  return {
    lesson_id: 7,
    study_plan_id: 3,
    target_language: 'es-ES',
    title: 'Pasado simple',
    cefr_level: 'A2',
    lesson_type: 'grammar',
    content_hash: 'hash',
    generator_version: '1',
    slides: [
      {
        id: 'slide-1',
        title: 'Pasado simple',
        bullets: ['Forma del pasado'],
        callout: null,
        reveal_steps: 1,
      },
      {
        id: 'slide-2',
        title: 'Cómo se forma',
        bullets: ['Raíz', 'Terminación'],
        callout: 'Yo hablé.',
        reveal_steps: 2,
      },
    ],
    segments: [
      {
        id: 'seg-1',
        order: 0,
        kind: 'hook',
        speech_text: 'Hoy miramos el pasado simple.',
        slide_id: 'slide-1',
        annotation_event_ids: ['ann-1'],
      },
      {
        id: 'seg-2',
        order: 1,
        kind: 'concept',
        speech_text: 'Primero la raíz, luego la terminación.',
        slide_id: 'slide-2',
        annotation_event_ids: ['ann-2'],
      },
      {
        id: 'seg-3',
        order: 2,
        kind: 'handoff',
        speech_text: 'Ahora practica con los ejercicios.',
        slide_id: 'slide-1',
        annotation_event_ids: [],
      },
    ],
    annotations: [
      {
        id: 'ann-1',
        segment_id: 'seg-1',
        at: 'segment_start',
        speech_fraction: null,
        op: 'underline',
        target_field: 'title',
        target_index: null,
        substring: 'Pasado',
        payload: 'Pasado',
      },
      {
        id: 'ann-2',
        segment_id: 'seg-2',
        at: 'segment_start',
        speech_fraction: null,
        op: 'margin_note',
        target_field: 'title',
        target_index: null,
        substring: null,
        payload: 'mira la raíz',
      },
    ],
    ...overrides,
  }
}

function session(
  overrides: Partial<ClassroomSessionResponse> = {}
): ClassroomSessionResponse {
  return {
    status: 'ready',
    mode: 'lecture',
    pack: pack(),
    fallback_deck: deck(),
    preparing: false,
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LessonClassroomEntry', () => {
  it('links to the classroom route', () => {
    render(<LessonClassroomEntry lessonId={7} />)
    const link = screen.getByRole('link', { name: /Classroom with Lingu/i })
    expect(link).toHaveAttribute('href', '/lesson/7/classroom')
  })
})

describe('ClassroomPresenter', () => {
  it('fires segment_start annotations on play without clarify', () => {
    render(<ClassroomPresenter pack={pack()} />)
    expect(screen.queryByText('Pasado')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Play lecture' }))
    expect(screen.getByText('Pasado')).toBeInTheDocument()
    expect(
      mocks.apiFetch.mock.calls.every(
        ([url]) => typeof url === 'string' && !url.includes('/classroom/clarify')
      )
    ).toBe(true)
  })

  it('clears marks when changing segment without autoplay', () => {
    render(<ClassroomPresenter pack={pack()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Play lecture' }))
    expect(screen.getByText('Pasado')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.queryByText('Pasado')).not.toBeInTheDocument()
    expect(screen.queryByText('mira la raíz')).not.toBeInTheDocument()
  })

  it('does not show Annotate in primary help', () => {
    render(<ClassroomPresenter pack={pack()} />)
    expect(
      screen.queryByRole('button', { name: /Annotate/i })
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rephrase' })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'More examples' })
    ).toBeInTheDocument()
  })

  it('auto-advances on ended while playing', () => {
    render(<ClassroomPresenter pack={pack()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Play lecture' }))
    expect(screen.getByTestId('audio-player')).toHaveAttribute(
      'data-text',
      'Hoy miramos el pasado simple.'
    )
    fireEvent.click(screen.getByRole('button', { name: 'end-audio' }))
    expect(screen.getByTestId('audio-player')).toHaveAttribute(
      'data-text',
      'Primero la raíz, luego la terminación.'
    )
  })

  it('reading fallback advances beats and repeats without clarify', () => {
    render(<ClassroomPresenter deck={deck()} />)
    expect(screen.getByTestId('audio-player')).toHaveAttribute(
      'data-plan',
      '3'
    )
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Usamos el pretérito.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Repeat' }))
    expect(mocks.apiFetch).not.toHaveBeenCalled()
  })

  it('calls clarify for rephrase and keeps exercise APIs unused', async () => {
    mocks.apiFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          spoken_text: 'Usamos el pasado.',
          display_text: 'Usamos el pasado.',
          annotations: [
            { beat_id: 'explanation-0', type: 'margin_note', payload: 'pasado' },
          ],
        }),
        { status: 200 }
      )
    )
    render(<ClassroomPresenter deck={deck()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: 'Rephrase' }))
    await waitFor(() => {
      expect(mocks.apiFetch).toHaveBeenCalledWith(
        '/api/lessons/7/classroom/clarify',
        expect.objectContaining({ method: 'POST' })
      )
    })
    expect(
      mocks.apiFetch.mock.calls.every(
        ([url]) =>
          typeof url === 'string' &&
          !url.includes('/complete') &&
          !url.includes('/answer')
      )
    ).toBe(true)
    await screen.findByText('Usamos el pasado.')
    expect(screen.getByText('pasado')).toBeInTheDocument()
  })
})

describe('LessonClassroomPage', () => {
  it('loads the deck session endpoint', async () => {
    mocks.apiFetch.mockResolvedValue(
      new Response(JSON.stringify(session()), { status: 200 })
    )
    render(<LessonClassroomPage />)
    await waitFor(() => {
      expect(mocks.apiFetch).toHaveBeenCalledWith(
        '/api/lessons/7/classroom/deck'
      )
    })
    expect(await screen.findByText('Part 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play lecture' })).toBeInTheDocument()
  })

  it('shows preparing reading mode while generating', async () => {
    mocks.apiFetch.mockResolvedValue(
      new Response(
        JSON.stringify(
          session({
            status: 'generating',
            mode: 'reading',
            pack: null,
            preparing: true,
          })
        ),
        { status: 200 }
      )
    )
    render(<LessonClassroomPage />)
    expect(
      await screen.findByText(/Preparing full lecture/i)
    ).toBeInTheDocument()
    expect(screen.getAllByText('Pasado simple').length).toBeGreaterThan(0)
  })
})
