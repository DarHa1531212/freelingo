'use client'

import { useTranslations } from 'next-intl'
import type { ClassroomClarifyAction } from './types'

const ACTIONS: ClassroomClarifyAction[] = ['rephrase', 'more_examples']

export function HelpPanel({
  busy,
  onRepeat,
  onClarify,
}: {
  busy: boolean
  onRepeat: () => void
  onClarify: (action: ClassroomClarifyAction) => void
}) {
  const t = useTranslations('classroom')

  return (
    <div className="border-fl-border bg-fl-surface flex flex-wrap gap-2 border px-4 py-3">
      <p className="text-fl-label text-fl-muted-2 w-full font-mono tracking-widest uppercase">
        {t('helpTitle')}
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={onRepeat}
        className="border-fl-border text-fl-fg hover:bg-fl-surface-2 disabled:text-fl-muted-4 border px-3 py-2 font-sans text-sm transition-colors disabled:cursor-not-allowed"
      >
        {t('repeat')}
      </button>
      {ACTIONS.map((action) => (
        <button
          key={action}
          type="button"
          disabled={busy}
          onClick={() => onClarify(action)}
          className="border-fl-border text-fl-fg hover:bg-fl-surface-2 disabled:text-fl-muted-4 border px-3 py-2 font-sans text-sm transition-colors disabled:cursor-not-allowed"
        >
          {t(`actions.${action}`)}
        </button>
      ))}
    </div>
  )
}
