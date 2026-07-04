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
import {
  createGame,
  deleteGame,
  errorMessage,
  getSeasons,
  listGames,
  startSeason,
} from '../lib/api'
import type { RatingStrategy } from '../lib/types'

/** Current-season badge + guarded "new season" action for one game. */
function SeasonControls({ gameId }: { gameId: number }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)

  const { data } = useQuery({
    queryKey: ['seasons', gameId],
    queryFn: () => getSeasons(gameId),
  })

  const start = useMutation({
    mutationFn: () => startSeason(gameId),
    onSuccess: () => {
      setConfirming(false)
      queryClient.invalidateQueries({ queryKey: ['seasons', gameId] })
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
    },
  })

  if (!data) return null
  return (
    <span className="mr-3 inline-flex items-center gap-2 text-xs">
      <span className="rounded bg-raised px-1.5 py-0.5 font-medium text-mute">
        Season {data.current_season}
      </span>
      {confirming ? (
        <>
          <span className="text-warn">
            Reset everyone's RD and re-open the ladder?
          </span>
          <button
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="rounded bg-warn/15 px-2 py-1 font-semibold text-warn hover:bg-warn/25 disabled:opacity-50"
          >
            {start.isPending ? 'Starting…' : 'Start season'}
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="rounded bg-raised px-2 py-1 font-medium hover:bg-line"
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          onClick={() => setConfirming(true)}
          className="rounded bg-raised px-2 py-1 font-medium text-mute hover:bg-line"
        >
          New season
        </button>
      )}
    </span>
  )
}

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
                  <p className="text-sm text-faint">
                    {game.description || 'No description'}
                    <span className="ml-2 rounded bg-raised px-1.5 py-0.5 text-xs font-medium text-mute">
                      {game.rating_strategy}
                    </span>
                  </p>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-y-2">
                  {confirmDeleteId !== game.id && (
                    <SeasonControls gameId={game.id} />
                  )}
                  {confirmDeleteId === game.id ? (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-loss">
                        Delete "{game.name}" and all its ratings?
                      </span>
                      <button
                        onClick={() => remove.mutate(game.id)}
                        className="rounded border border-loss/40 bg-loss/10 px-3 py-1.5 text-xs font-semibold text-loss hover:bg-loss/20"
                      >
                        Delete
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(null)}
                        className="rounded bg-raised px-3 py-1.5 text-xs font-medium hover:bg-line"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmDeleteId(game.id)}
                      className="rounded bg-raised px-3 py-1.5 text-xs font-medium text-mute hover:bg-loss/10 hover:text-loss"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>

        <Card className="h-fit p-4">
          <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wider text-mute">New game</h2>
          <label className="block font-display text-xs font-semibold uppercase tracking-wider text-faint">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Pickleball"
              className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm text-ink focus:border-ember focus:outline-none"
            />
          </label>
          <label className="mt-3 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
            Description (optional)
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm text-ink focus:border-ember focus:outline-none"
            />
          </label>
          <label className="mt-3 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
            Rating strategy
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as RatingStrategy)}
              className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm text-ink focus:border-ember focus:outline-none"
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
            className="mt-4 w-full rounded bg-ember py-2 font-semibold text-ember-ink hover:bg-ember-bright disabled:opacity-40"
          >
            {create.isPending ? 'Creating…' : 'Create Game'}
          </button>
          {create.error && (
            <p className="mt-2 text-sm text-loss">
              {errorMessage(create.error)}
            </p>
          )}
        </Card>
      </div>
    </div>
  )
}
