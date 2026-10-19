'use client'

import { useTranslations } from 'next-intl'
import { TargetLanguageText } from '@/components/TargetLanguageText'
import type { ClassroomGrammarTable } from './types'

export function GrammarTablesPanel({
  tables,
  targetLanguage,
}: {
  tables: ClassroomGrammarTable[]
  targetLanguage: string
}) {
  const t = useTranslations('classroom')
  if (tables.length === 0) return null

  return (
    <div className="border-fl-border bg-fl-surface space-y-6 border px-6 py-6">
      <p className="text-fl-label text-fl-muted-2 font-mono tracking-widest uppercase">
        {t('conjugationTables')}
      </p>
      {tables.map((table) => (
        <div key={`${table.slug}-${table.headers.join('|')}`} className="space-y-3">
          <TargetLanguageText
            languageCode={targetLanguage}
            as="p"
            className="text-fl-fg font-sans text-base font-medium"
          >
            {table.title}
          </TargetLanguageText>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {table.headers.map((header) => (
                    <th
                      key={header}
                      className="text-fl-label text-fl-muted-2 border-fl-border border px-3 py-1.5 text-left font-mono tracking-widest uppercase"
                    >
                      <TargetLanguageText languageCode={targetLanguage} as="span">
                        {header}
                      </TargetLanguageText>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, rowIndex) => (
                  <tr key={`${table.slug}-row-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td
                        key={`${table.slug}-${rowIndex}-${cellIndex}`}
                        className="text-fl-fg border-fl-border border px-3 py-1.5 font-mono text-sm"
                      >
                        <TargetLanguageText languageCode={targetLanguage} as="span">
                          {cell}
                        </TargetLanguageText>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
