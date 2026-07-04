import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  Button,
  Card,
  CardTitle,
  ConfirmButton,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Pill,
  SegmentedControl,
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
import type { Game, RatingStrategy } from '../lib/types'

/** Compact read-only summary of a game's tuning knobs, if any are set. */
function configSummary(game: Game): string | null {
  const config = game.rating_config ?? {}
  const parts: string[] = []
  const labels: [string, string][] = [
    ['tau', 'tau'],
    ['score_preset', 'preset'],
    ['min_swing', 'min swing'],
    ['margin_weight_factor', 'margin weight'],
    ['season_rd_reset', 'season RD reset'],
    ['rd_growth_period_days', 'RD growth days'],
    ['leaderboard_mode', 'board'],
  ]
  for (const [key, label] of labels) {
    const value = config[key]
    if (typeof value === 'number' || typeof value === 'string')
      parts.push(`${label} ${value}`)
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

/** Current-season badge + guarded "new season" action for one game. */
function SeasonControls({ gameId }: { gameId: number }) {
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ['seasons', gameId],
    queryFn: () => getSeasons(gameId),
  })

  const start = useMutation({
    mutationFn: () => startSeason(gameId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seasons', gameId] })
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
    },
  })

  if (!data) return null
  return (
    <span className="mr-2 inline-flex items-center gap-2 text-xs">
      <span className="rounded bg-raised px-1.5 py-0.5 font-data font-medium text-mute">
        Season {data.current_season}
      </span>
      <ConfirmButton
        prompt="Reset everyone's RD and re-open the ladder?"
        confirmLabel="Start season"
        busyLabel="Starting…"
        busy={start.isPending}
        onConfirm={() => start.mutate()}
      >
        New season
      </ConfirmButton>
    </span>
  )
}

export default function GamesPage() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [strategy, setStrategy] = useState<RatingStrategy>('glicko2')
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
      {remove.error && <ErrorNote message={errorMessage(remove.error)} />}

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
            {data?.items.map((game) => {
              const summary = configSummary(game)
              return (
                <Card
                  key={game.id}
                  className="flex flex-wrap items-center justify-between gap-3 p-4"
                >
                  <div className="min-w-0">
                    <p className="flex items-center gap-2">
                      <span className="font-display text-lg font-semibold uppercase tracking-wide">
                        {game.name}
                      </span>
                      <Pill tone={game.rating_strategy === 'glicko2' ? 'flag' : 'draw'}>
                        {game.rating_strategy}
                      </Pill>
                    </p>
                    <p className="text-sm text-faint">
                      {game.description || 'No description'}
                    </p>
                    {summary && (
                      <p className="mt-1 font-data text-xs text-faint">
                        {summary}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-y-2">
                    <SeasonControls gameId={game.id} />
                    <ConfirmButton
                      prompt={`Delete "${game.name}" and all its ratings?`}
                      confirmLabel="Delete"
                      busyLabel="Deleting…"
                      busy={remove.isPending}
                      onConfirm={() => remove.mutate(game.id)}
                    >
                      Delete
                    </ConfirmButton>
                  </div>
                </Card>
              )
            })}
          </div>
        </div>

        <Card className="h-fit p-4">
          <CardTitle className="mb-3">New game</CardTitle>
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Pickleball"
            />
          </Field>
          <Field label="Description (optional)" className="mt-3">
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          <Field
            label="Rating strategy"
            className="mt-3"
            hint={
              strategy === 'glicko2'
                ? 'Glicko-2: full ratings, predictions, matchmaking.'
                : 'No ratings — just track matches.'
            }
          >
            <SegmentedControl
              options={[
                { value: 'glicko2', label: 'Glicko-2' },
                { value: 'dummy', label: 'Track only' },
              ]}
              value={strategy}
              onChange={(v) => setStrategy(v as RatingStrategy)}
            />
          </Field>
          <Button
            variant="primary"
            onClick={() =>
              create.mutate({
                name: name.trim(),
                rating_strategy: strategy,
                description: description.trim() || undefined,
              })
            }
            disabled={name.trim().length < 2 || create.isPending}
            className="mt-4 w-full"
          >
            {create.isPending ? 'Creating…' : 'Create game'}
          </Button>
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
