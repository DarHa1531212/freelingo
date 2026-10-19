'use client'

import { useTranslations } from 'next-intl'
import { TargetLanguageText } from '@/components/TargetLanguageText'
import type {
  ClassroomAnnotationOp,
  ClassroomBeat,
  SlideFrame,
} from './types'

function applyMarks(
  text: string,
  annotations: ClassroomAnnotationOp[]
): Array<{ text: string; mark?: 'highlight' | 'underline' }> {
  const marks = annotations.filter(
    (item) => item.type === 'highlight' || item.type === 'underline'
  )
  if (marks.length === 0) return [{ text }]

  const mark = marks[0]
  const index = text.indexOf(mark.payload)
  if (index < 0) return [{ text }]
  const before = text.slice(0, index)
  const mid = text.slice(index, index + mark.payload.length)
  const after = text.slice(index + mark.payload.length)
  const parts: Array<{ text: string; mark?: 'highlight' | 'underline' }> = []
  if (before) parts.push({ text: before })
  parts.push({ text: mid, mark: mark.type })
  if (after) parts.push({ text: after })
  return parts
}

function MarkedText({
  text,
  annotations,
  targetLanguage,
  className,
}: {
  text: string
  annotations: ClassroomAnnotationOp[]
  targetLanguage: string
  className: string
}) {
  const parts = applyMarks(text, annotations)
  return (
    <TargetLanguageText
      languageCode={targetLanguage}
      as="p"
      className={className}
    >
      {parts.map((part, index) =>
        part.mark === 'highlight' ? (
          <mark
            key={`${part.text}-${index}`}
            className="bg-fl-accent/20 text-fl-fg rounded-sm px-0.5"
          >
            {part.text}
          </mark>
        ) : part.mark === 'underline' ? (
          <span
            key={`${part.text}-${index}`}
            className="decoration-fl-accent underline decoration-2 underline-offset-4"
          >
            {part.text}
          </span>
        ) : (
          <span key={`${part.text}-${index}`}>{part.text}</span>
        )
      )}
    </TargetLanguageText>
  )
}

function fieldAnnotations(
  annotations: ClassroomAnnotationOp[],
  field: 'title' | 'callout' | 'bullet' | 'primary',
  index?: number
) {
  return annotations.filter((item) => {
    const target = item.target_field ?? 'primary'
    if (target !== field) return false
    if (field === 'bullet') return (item.target_index ?? 0) === (index ?? 0)
    return true
  })
}

export function WhiteboardBoard({
  beat,
  slide,
  visibleBullets,
  kindLabel,
  annotations,
  helpText,
  targetLanguage,
}: {
  beat?: ClassroomBeat | null
  slide?: SlideFrame | null
  visibleBullets?: number
  kindLabel: string
  annotations: ClassroomAnnotationOp[]
  helpText: string | null
  targetLanguage: string
}) {
  const t = useTranslations('classroom')
  const marginNotes = annotations.filter((item) => item.type === 'margin_note')
  const bullets = slide?.bullets.slice(0, visibleBullets ?? slide.bullets.length) ?? []

  return (
    <div className="border-fl-border bg-fl-surface grid gap-4 border md:grid-cols-[minmax(0,1fr)_12rem]">
      <div className="space-y-4 px-6 py-8">
        {beat?.title && (
          <p className="text-fl-label text-fl-muted-2 font-mono tracking-widest uppercase">
            {beat.title}
          </p>
        )}
        <p className="text-fl-label text-fl-muted-2 font-mono tracking-widest uppercase">
          {kindLabel}
        </p>
        {slide ? (
          <>
            <MarkedText
              text={slide.title}
              annotations={fieldAnnotations(annotations, 'title')}
              targetLanguage={targetLanguage}
              className="text-fl-fg text-xl font-medium leading-relaxed"
            />
            {bullets.length > 0 && (
              <ul className="text-fl-fg space-y-2 text-lg leading-relaxed">
                {bullets.map((bullet, index) => (
                  <li key={`${bullet}-${index}`} className="flex gap-2">
                    <span className="text-fl-muted-3">•</span>
                    <MarkedText
                      text={bullet}
                      annotations={fieldAnnotations(annotations, 'bullet', index)}
                      targetLanguage={targetLanguage}
                      className="text-fl-fg text-lg leading-relaxed"
                    />
                  </li>
                ))}
              </ul>
            )}
            {slide.callout && (
              <div className="border-fl-border bg-fl-surface-2 border px-4 py-3">
                <MarkedText
                  text={slide.callout}
                  annotations={fieldAnnotations(annotations, 'callout')}
                  targetLanguage={targetLanguage}
                  className="text-fl-fg text-base leading-relaxed"
                />
              </div>
            )}
          </>
        ) : beat ? (
          <>
            <MarkedText
              text={beat.primary_text}
              annotations={fieldAnnotations(annotations, 'primary').length
                ? fieldAnnotations(annotations, 'primary')
                : annotations.filter(
                    (item) =>
                      item.type === 'highlight' || item.type === 'underline'
                  )}
              targetLanguage={targetLanguage}
              className="text-fl-fg text-xl leading-relaxed"
            />
            {beat.secondary_text && (
              <TargetLanguageText
                languageCode={targetLanguage}
                as="p"
                className="text-fl-muted-3 text-base leading-relaxed"
              >
                {beat.secondary_text}
              </TargetLanguageText>
            )}
          </>
        ) : null}
        {helpText && (
          <div className="border-fl-border bg-fl-surface-2 border px-4 py-3">
            <p className="text-fl-label text-fl-muted-2 mb-2 font-mono tracking-widest uppercase">
              {t('helpNote')}
            </p>
            <TargetLanguageText
              languageCode={targetLanguage}
              as="p"
              className="text-fl-fg text-base leading-relaxed"
            >
              {helpText}
            </TargetLanguageText>
          </div>
        )}
      </div>
      <aside className="border-fl-border space-y-3 border-t px-4 py-6 md:border-t-0 md:border-l">
        <p className="text-fl-label text-fl-muted-2 font-mono tracking-widest uppercase">
          {t('margin')}
        </p>
        {marginNotes.length === 0 ? (
          <p className="text-fl-muted-4 font-sans text-sm">{t('marginEmpty')}</p>
        ) : (
          marginNotes.map((note, index) => (
            <TargetLanguageText
              key={`${note.payload}-${index}`}
              languageCode={targetLanguage}
              as="p"
              className="text-fl-fg border-fl-border border px-3 py-2 text-sm leading-relaxed"
            >
              {note.payload}
            </TargetLanguageText>
          ))
        )}
      </aside>
    </div>
  )
}
