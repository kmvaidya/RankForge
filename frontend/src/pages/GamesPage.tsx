import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  Spinner,
  SuccessNote,
} from '../components/ui'
import { createGame, deleteGame, errorMessage, listGames } from '../lib/api'
import type { RatingStrategy } from '../lib/types'

export default function GamesPage() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [strategy, setStrategy] = useState<RatingStrategy>('glicko2')
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const { data, isPending, error } = useQuery({
    queryKey: ['games'],
    queryFn: listGames,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['games'] })

  const create = useMutation({
    mutationFn: createGame,
    onSuccess: (game) => {
      setName('')
      setDescription('')
      setNotice(`Game "${game.name}" created.`)
      invalidate()
    },
  })

  const remove = useMutation({
    mutationFn: deleteGame,
    onSuccess: () => {
      setConfirmDeleteId(null)
      setNotice('Game deleted.')
      invalidate()
    },
  })

  return (
    <div>
      <PageHeader title="Games" subtitle="Each game keeps its own ratings" />

      {notice && (
        <div className="mb-4">
          <SuccessNote>{notice}</SuccessNote>
        </div>
      )}
      {error && <ErrorNote message={errorMessage(error)} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          {isPending && <Spinner />}
          {data && data.items.length === 0 && (
            <EmptyState
              title="No games yet"
              hint="Create your first game to start tracking ratings."
            />
          )}
          <div className="space-y-3">
            {data?.items.map((game) => (
              <Card key={game.id} className="flex items-center justify-between p-4">
                <div>
                  <p className="font-semibold">{game.name}</p>
                  <p className="text-sm text-slate-500">
                    {game.description || 'No description'}
                    <span className="ml-2 rounded bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-400">
                      {game.rating_strategy}
                    </span>
                  </p>
                </div>
                {confirmDeleteId === game.id ? (
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-red-400">
                      Delete "{game.name}" and all its ratings?
                    </span>
                    <button
                      onClick={() => remove.mutate(game.id)}
                      className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-600"
                    >
                      Delete
                    </button>
                    <button
                      onClick={() => setConfirmDeleteId(null)}
                      className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium hover:bg-slate-700"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDeleteId(game.id)}
                    className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-red-950 hover:text-red-300"
                  >
                    Delete
                  </button>
                )}
              </Card>
            ))}
          </div>
        </div>

        <Card className="h-fit p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">New game</h2>
          <label className="block text-xs font-medium text-slate-400">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Pickleball"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-slate-400">
            Description (optional)
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-slate-400">
            Rating strategy
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as RatingStrategy)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="glicko2">Glicko-2 (recommended)</option>
              <option value="dummy">None (track matches only)</option>
            </select>
          </label>
          <button
            onClick={() =>
              create.mutate({
                name: name.trim(),
                rating_strategy: strategy,
                description: description.trim() || undefined,
              })
            }
            disabled={name.trim().length < 2 || create.isPending}
            className="mt-4 w-full rounded-lg bg-indigo-600 py-2 font-semibold text-white hover:bg-indigo-500 disabled:opacity-40"
          >
            {create.isPending ? 'Creating…' : 'Create Game'}
          </button>
          {create.error && (
            <p className="mt-2 text-sm text-red-400">
              {errorMessage(create.error)}
            </p>
          )}
        </Card>
      </div>
    </div>
  )
}
