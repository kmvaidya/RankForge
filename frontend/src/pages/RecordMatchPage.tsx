import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import BulkAddPlayers from '../components/BulkAddPlayers'
import {
  Card,
  ErrorNote,
  PageHeader,
  Pill,
  RatingDelta,
  Spinner,
  SuccessNote,
  WinProbBar,
} from '../components/ui'
import {
  createMatch,
  createPlayer,
  errorMessage,
  listGames,
  listPlayers,
  predictMatch,
} from '../lib/api'
import { useFeature } from '../lib/features'
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
  const [score1, setScore1] = useState('')
  const [score2, setScore2] = useState('')
  const [notes, setNotes] = useState('')
  const [weight, setWeight] = useState('')
  const weightsEnabled = useFeature('match_weights')
  const weightValue = weight.trim() === '' ? 1 : Number(weight)
  const weightValid = Number.isFinite(weightValue) && weightValue > 0

  // The selected game's quick-entry preset (rating_config.score_preset):
  // tapping the winner auto-fills scores preset-0 for two-tap recording.
  const { data: gamesData } = useQuery({ queryKey: ['games'], queryFn: listGames })
  const selectedGame = gamesData?.items.find((g) => g.id === gameId)
  const scorePreset = selectedGame?.rating_config?.score_preset
  const preset = typeof scorePreset === 'number' ? scorePreset : null

  const parseScore = (raw: string): number | null => {
    if (raw.trim() === '') return null
    const n = Number(raw)
    return Number.isFinite(n) && n >= 0 ? n : null
  }
  const s1 = parseScore(score1)
  const s2 = parseScore(score2)
  const scoresValid =
    (score1.trim() === '' && score2.trim() === '') || (s1 !== null && s2 !== null)
  const [newPlayerName, setNewPlayerName] = useState('')
  const [result, setResult] = useState<Match | null>(null)
  /** Set at submit time when the recorded winner defied the odds. */
  const [upset, setUpset] = useState<{ team: number; odds: number } | null>(null)

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = playersData?.items ?? []

  // Live pre-match odds from the rating engine, once both sides have players.
  const canPredict = gameId !== null && team1.length > 0 && team2.length > 0
  const prediction = useQuery({
    queryKey: [
      'predict',
      gameId,
      [...team1].sort((a, b) => a - b).join(','),
      [...team2].sort((a, b) => a - b).join(','),
    ],
    queryFn: () => predictMatch(gameId!, [team1, team2]),
    enabled: canPredict,
    staleTime: 30_000,
  })
  const odds = prediction.data

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
      setScore1('')
      setScore2('')
      setNotes('')
      setWeight('')
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
    gameId !== null &&
    team1.length > 0 &&
    team2.length > 0 &&
    weightValid &&
    scoresValid &&
    !submit.isPending

  /** Two-tap entry: picking the winner also drafts the score line when the
   *  game has a preset and nothing has been typed yet. */
  const pickWinner = (value: Winner) => {
    setWinner(value)
    if (preset === null || value === 'draw') return
    if (score1.trim() === '' && score2.trim() === '') {
      setScore1(String(value === 1 ? preset : 0))
      setScore2(String(value === 2 ? preset : 0))
    }
  }

  const handleSubmit = () => {
    if (!canSubmit) return
    // Judge the upset from the odds as they stood at submit time.
    if (winner !== 'draw' && odds) {
      const winnerOdds = odds.teams[winner - 1]?.win_probability
      setUpset(
        winnerOdds !== undefined && winnerOdds < 0.35
          ? { team: winner, odds: winnerOdds }
          : null,
      )
    } else {
      setUpset(null)
    }
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
    if (s1 !== null && s2 !== null) {
      metadata.team_scores = { '1': s1, '2': s2 }
      metadata.final_score = `${s1}-${s2}`
    }
    if (notes.trim()) metadata.notes = notes.trim()
    if (weightsEnabled && weight.trim() && weightValue !== 1)
      metadata.weight = weightValue

    submit.mutate({
      game_id: gameId!,
      participants,
      match_metadata: metadata,
    })
  }

  const teamBox = (team: 1 | 2, ids: number[]) => (
    <div
      className={`rounded border p-3 ${
        winner === team
          ? 'border-win/60 bg-win/5'
          : 'border-line'
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="font-display text-sm font-semibold uppercase tracking-wider text-mute">
          Team {team}
        </span>
        <span className="text-xs text-faint">{ids.length} player(s)</span>
      </div>
      <div className="flex min-h-8 flex-wrap gap-1.5">
        {ids.map((id) => (
          <span
            key={id}
            className="rounded-full bg-raised px-2.5 py-1 text-xs font-medium"
          >
            {players.find((p) => p.id === id)?.name ?? id}
          </span>
        ))}
        {ids.length === 0 && (
          <span className="text-xs text-faint">
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
      />

      {result && (
        <div className="mb-6 space-y-3">
          <SuccessNote>
            Match #{result.id} recorded — rating changes below.
            {upset && (
              <span className="ml-2 font-semibold text-warn">
                Upset! Team {upset.team} won at{' '}
                {Math.round(upset.odds * 100)}% odds.
              </span>
            )}
          </SuccessNote>
          <Card className="p-4">
            <div className="grid gap-2 sm:grid-cols-2">
              {result.participants.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between rounded bg-raised px-3 py-2"
                >
                  <span className="font-medium">
                    <Link
                      to={`/players/${p.player.id}`}
                      className="hover:underline"
                    >
                      {p.player.name}
                    </Link>
                    <span className="ml-2 text-xs text-faint">
                      Team {p.team_id}
                    </span>
                  </span>
                  <span className="font-data">
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

          {canPredict && odds && odds.teams.length === 2 && (
            <Card className="p-3">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="font-semibold font-data text-mute">
                  {Math.round(odds.teams[0].win_probability * 100)}%
                </span>
                <span className="flex items-center gap-2 text-faint">
                  Pre-match odds
                  {odds.lopsided && <Pill tone="warn">lopsided matchup</Pill>}
                </span>
                <span className="font-semibold font-data text-mute">
                  {Math.round(odds.teams[1].win_probability * 100)}%
                </span>
              </div>
              <WinProbBar probability={odds.teams[0].win_probability} />
            </Card>
          )}

          <Card className="p-4">
            <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wider text-mute">
              Assign players
            </h2>
            {isPending && <Spinner />}
            <div className="grid gap-1.5 sm:grid-cols-2">
              {players.map((player) => {
                const team = assignment(player.id)
                return (
                  <div
                    key={player.id}
                    className="flex items-center justify-between rounded border border-line px-3 py-1.5"
                  >
                    <span className="text-sm font-medium">{player.name}</span>
                    <div className="flex gap-1">
                      {([1, 2] as const).map((t) => (
                        <button
                          key={t}
                          onClick={() => toggle(player.id, t)}
                          className={`rounded px-2 py-0.5 text-xs font-semibold transition-colors ${
                            team === t
                              ? 'bg-ember text-ember-ink'
                              : 'bg-raised text-mute hover:bg-line'
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
                className="flex-1 rounded border border-line-strong bg-raised px-3 py-1.5 text-sm focus:border-ember focus:outline-none"
              />
              <button
                onClick={() => addPlayer.mutate(newPlayerName.trim())}
                disabled={newPlayerName.trim().length < 2 || addPlayer.isPending}
                className="rounded bg-raised px-3 py-1.5 text-sm font-medium hover:bg-line disabled:opacity-50"
              >
                Add player
              </button>
            </div>
            {addPlayer.error && (
              <p className="mt-2 text-sm text-loss">
                {errorMessage(addPlayer.error)}
              </p>
            )}
            <BulkAddPlayers />
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wider text-mute">Result</h2>
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
                  onClick={() => pickWinner(value)}
                  className={`rounded px-2 py-2 text-xs font-semibold transition-colors ${
                    winner === value
                      ? 'bg-ember text-ember-ink'
                      : 'bg-raised text-mute hover:bg-line'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-4 grid grid-cols-2 gap-2">
              {(
                [
                  ['Team 1 score', score1, setScore1],
                  ['Team 2 score', score2, setScore2],
                ] as const
              ).map(([label, value, setter]) => (
                <label
                  key={label}
                  className="block font-display text-xs font-semibold uppercase tracking-wider text-faint"
                >
                  {label}
                  <input
                    value={value}
                    onChange={(e) => setter(e.target.value)}
                    inputMode="numeric"
                    placeholder={preset !== null ? String(preset) : '—'}
                    className={`mt-1 w-full rounded border bg-raised px-3 py-1.5 text-sm text-ink focus:outline-none ${
                      scoresValid
                        ? 'border-line-strong focus:border-ember'
                        : 'border-loss focus:border-loss'
                    }`}
                  />
                </label>
              ))}
            </div>
            {!scoresValid && (
              <p className="mt-1 text-xs text-loss">
                Enter both scores as non-negative numbers, or leave both empty.
              </p>
            )}

            {weightsEnabled && (
              <label className="mt-3 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Match weight (optional)
                <input
                  value={weight}
                  onChange={(e) => setWeight(e.target.value)}
                  inputMode="decimal"
                  placeholder="1 = normal, 5 = counts 5×"
                  className={`mt-1 w-full rounded border bg-raised px-3 py-1.5 text-sm text-ink focus:outline-none ${
                    weightValid
                      ? 'border-line-strong focus:border-ember'
                      : 'border-loss focus:border-loss'
                  }`}
                />
                <span className="mt-1 block text-[11px] text-faint">
                  Scales how much this match moves ratings. Must be a positive
                  number.
                </span>
              </label>
            )}

            <label className="mt-3 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
              Notes (optional)
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm text-ink focus:border-ember focus:outline-none"
              />
            </label>

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="mt-4 w-full rounded bg-ember py-2.5 font-semibold text-ember-ink transition-colors hover:bg-ember-bright disabled:cursor-not-allowed disabled:opacity-40"
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
