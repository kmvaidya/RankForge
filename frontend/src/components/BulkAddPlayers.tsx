import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import axios from 'axios'

import { createPlayer } from '../lib/api'

type LineStatus = 'added' | 'duplicate' | 'error'

interface LineResult {
  name: string
  status: LineStatus
  detail?: string
}

const STATUS_STYLE: Record<LineStatus, string> = {
  added: 'text-emerald-400',
  duplicate: 'text-amber-400',
  error: 'text-red-400',
}

/** Paste-a-list player import: one name per line, per-line results.
 *  Duplicates are reported, not treated as failures — re-pasting a full
 *  club roster is the expected way to sync it. */
export default function BulkAddPlayers() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<LineResult[] | null>(null)

  const names = [
    ...new Set(
      text
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    ),
  ]

  const runImport = async () => {
    setBusy(true)
    const outcome: LineResult[] = []
    for (const name of names) {
      if (name.length < 2) {
        outcome.push({ name, status: 'error', detail: 'name too short' })
        continue
      }
      try {
        await createPlayer(name)
        outcome.push({ name, status: 'added' })
      } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 409) {
          outcome.push({ name, status: 'duplicate' })
        } else {
          outcome.push({
            name,
            status: 'error',
            detail: error instanceof Error ? error.message : 'failed',
          })
        }
      }
    }
    setResults(outcome)
    setText('')
    setBusy(false)
    queryClient.invalidateQueries({ queryKey: ['players'] })
  }

  const counts = results?.reduce(
    (acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }),
    {} as Partial<Record<LineStatus, number>>,
  )

  return (
    <div className="mt-3">
      <button
        onClick={() => {
          setOpen(!open)
          setResults(null)
        }}
        className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
      >
        {open ? '− Hide bulk add' : '+ Bulk add players (paste a list)'}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            placeholder={'One name per line:\nAlice\nBob\nCharlie'}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">
              {names.length} unique name{names.length === 1 ? '' : 's'} to
              import
            </span>
            <button
              onClick={runImport}
              disabled={names.length === 0 || busy}
              className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
            >
              {busy ? 'Importing…' : 'Import all'}
            </button>
          </div>

          {results && (
            <div className="rounded-lg border border-slate-800 p-2">
              <p className="mb-1 text-xs text-slate-400">
                {counts?.added ?? 0} added · {counts?.duplicate ?? 0} already
                existed · {counts?.error ?? 0} failed
              </p>
              <ul className="max-h-40 space-y-0.5 overflow-y-auto text-xs">
                {results.map((r, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span className="truncate">{r.name}</span>
                    <span className={STATUS_STYLE[r.status]}>
                      {r.status}
                      {r.detail ? ` — ${r.detail}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
