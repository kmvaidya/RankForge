import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import GamePicker from '../components/GamePicker'
import {
  Card,
  ErrorNote,
  PageHeader,
  RatingDelta,
  Spinner,
  SuccessNote,
} from '../components/ui'
import { createMatch, createPlayer, errorMessage, listPlayers } from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'
import type { Match, ParticipantCreate } from '../lib/types'

type Winner = 1 | 2 | 'draw'

/** Optional teams passed from the Matchmaking page via router state. */
interface PrefillState {
  team1?: number[]
  team2?: number[]
}

export default function RecordMatchPage() {
  const { gameId } = useSelectedGame()
  const queryClient = useQueryClient()
  const prefill = (useLocation().state ?? {}) as PrefillState

  const [team1, setTeam1] = useState<number[]>(prefill.team1 ?? [])
  const [team2, setTeam2] = useState<number[]>(prefill.team2 ?? [])
  const [winner, setWinner] = useState<Winner>(1)
  const [score, setScore] = useState('')
  const [notes, setNotes] = useState('')
  const [newPlayerName, setNewPlayerName] = useState('')
  const [result, setResult] = useState<Match | null>(null)

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = playersData?.items ?? []

  const addPlayer = useMutation({
    mutationFn: createPlayer,
    onSuccess: () => {
      setNewPlayerName('')
      queryClient.invalidateQueries({ queryKey: ['players'] })
    },
  })

  const submit = useMutation({
    mutationFn: createMatch,
    onSuccess: (match) => {
      setResult(match)
      setTeam1([])
      setTeam2([])
      setScore('')
      setNotes('')
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
      queryClient.invalidateQueries({ queryKey: ['matches'] })
    },
  })

  const assignment = (playerId: number): 1 | 2 | null =>
    team1.includes(playerId) ? 1 : team2.includes(playerId) ? 2 : null

  const toggle = (playerId: number, team: 1 | 2) => {
    setResult(null)
    const current = assignment(playerId)
    setTeam1((t) => t.filter((id) => id !== playerId))
    setTeam2((t) => t.filter((id) => id !== playerId))
    if (current !== team) {
      if (team === 1) setTeam1((t) => [...t, playerId])
      else setTeam2((t) => [...t, playerId])
    }
  }

  const canSubmit =
    gameId !== null && team1.length > 0 && team2.length > 0 && !submit.isPending

  const handleSubmit = () => {
    if (!canSubmit) return
    const outcomeFor = (team: 1 | 2) =>
      winner === 'draw'
        ? ({ result: 'draw' } as const)
        : winner === team
          ? ({ result: 'win' } as const)
          : ({ result: 'loss' } as const)

    const participants: ParticipantCreate[] = [
      ...team1.map((id) => ({
        player_id: id,
        team_id: 1,
        outcome: outcomeFor(1),
      })),
      ...team2.map((id) => ({
        player_id: id,
        team_id: 2,
        outcome: outcomeFor(2),
      })),
    ]

    const metadata: Record<string, unknown> = {}
    if (score.trim()) metadata.final_score = score.trim()
    if (notes.trim()) metadata.notes = notes.trim()

    submit.mutate({
      game_id: gameId!,
      participants,
      match_metadata: metadata,
    })
  }

  const teamBox = (team: 1 | 2, ids: number[]) => (
    <div
      className={`rounded-lg border p-3 ${
        winner === team
          ? 'border-emerald-700 bg-emerald-950/20'
          : 'border-slate-800'
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-300">
          Team {team}
        </span>
        <span className="text-xs text-slate-500">{ids.length} player(s)</span>
      </div>
      <div className="flex min-h-8 flex-wrap gap-1.5">
        {ids.map((id) => (
          <span
            key={id}
            className="rounded-full bg-slate-800 px-2.5 py-1 text-xs font-medium"
          >
            {players.find((p) => p.id === id)?.name ?? id}
          </span>
        ))}
        {ids.length === 0 && (
          <span className="text-xs text-slate-600">
            Select players below…
          </span>
        )}
      </div>
    </div>
  )

  return (
    <div>
      <PageHeader
        title="Record Match"
        subtitle="Ratings update the moment you submit"
        actions={<GamePicker />}
      />

      {result && (
        <div className="mb-6 space-y-3">
          <SuccessNote>
            Match #{result.id} recorded — rating changes below.
          </SuccessNote>
          <Card className="p-4">
            <div className="grid gap-2 sm:grid-cols-2">
              {result.participants.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="font-medium">
                    <Link
                      to={`/players/${p.player.id}`}
                      className="hover:underline"
                    >
                      {p.player.name}
                    </Link>
                    <span className="ml-2 text-xs text-slate-500">
                      Team {p.team_id}
                    </span>
                  </span>
                  <span className="tabular-nums">
                    {p.rating_info_before
                      ? Math.round(p.rating_info_before.rating)
                      : '—'}{' '}
                    →{' '}
                    {p.rating_info_before && p.rating_info_change ? (
                      <>
                        <strong>
                          {Math.round(
                            p.rating_info_before.rating +
                              p.rating_info_change.rating_change,
                          )}
                        </strong>{' '}
                        (<RatingDelta value={p.rating_info_change.rating_change} />)
                      </>
                    ) : (
                      '—'
                    )}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {teamBox(1, team1)}
            {teamBox(2, team2)}
          </div>

          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">
              Assign players
            </h2>
            {isPending && <Spinner />}
            <div className="grid gap-1.5 sm:grid-cols-2">
              {players.map((player) => {
                const team = assignment(player.id)
                return (
                  <div
                    key={player.id}
                    className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-1.5"
                  >
                    <span className="text-sm font-medium">{player.name}</span>
                    <div className="flex gap-1">
                      {([1, 2] as const).map((t) => (
                        <button
                          key={t}
                          onClick={() => toggle(player.id, t)}
                          className={`rounded px-2 py-0.5 text-xs font-semibold transition-colors ${
                            team === t
                              ? 'bg-indigo-600 text-white'
                              : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                          }`}
                        >
                          T{t}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>

            <div className="mt-4 flex gap-2">
              <input
                value={newPlayerName}
                onChange={(e) => setNewPlayerName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newPlayerName.trim().length >= 2)
                    addPlayer.mutate(newPlayerName.trim())
                }}
                placeholder="New player name…"
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
              <button
                onClick={() => addPlayer.mutate(newPlayerName.trim())}
                disabled={newPlayerName.trim().length < 2 || addPlayer.isPending}
                className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
              >
                Add player
              </button>
            </div>
            {addPlayer.error && (
              <p className="mt-2 text-sm text-red-400">
                {errorMessage(addPlayer.error)}
              </p>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Result</h2>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  [1, 'Team 1 won'],
                  ['draw', 'Draw'],
                  [2, 'Team 2 won'],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={String(value)}
                  onClick={() => setWinner(value)}
                  className={`rounded-lg px-2 py-2 text-xs font-semibold transition-colors ${
                    winner === value
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <label className="mt-4 block text-xs font-medium text-slate-400">
              Score (optional)
              <input
                value={score}
                onChange={(e) => setScore(e.target.value)}
                placeholder="e.g. 11-8"
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </label>

            <label className="mt-3 block text-xs font-medium text-slate-400">
              Notes (optional)
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </label>

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="mt-4 w-full rounded-lg bg-indigo-600 py-2.5 font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submit.isPending ? 'Submitting…' : 'Submit Match'}
            </button>
            {submit.error && (
              <div className="mt-3">
                <ErrorNote message={errorMessage(submit.error)} />
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
