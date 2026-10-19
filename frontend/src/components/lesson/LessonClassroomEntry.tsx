'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Presentation } from 'lucide-react'

export function LessonClassroomEntry({ lessonId }: { lessonId: number }) {
  const t = useTranslations('classroom')

  return (
    <Link
      href={`/lesson/${lessonId}/classroom`}
      className="border-fl-border text-fl-fg hover:bg-fl-surface-2 inline-flex items-center justify-center gap-2 border px-4 py-3 font-sans text-sm transition-colors"
    >
      <Presentation className="size-4 shrink-0" aria-hidden="true" />
      {t('entry')}
    </Link>
  )
}
