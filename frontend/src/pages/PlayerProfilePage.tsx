import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  RatingDelta,
  Spinner,
} from '../components/ui'
import { errorMessage, getPlayerMatches, getPlayerStats } from '../lib/api'
import { outcomeLabel } from '../lib/outcome'
import type { Match } from '../lib/types'

function playerOutcomeLabel(match: Match, playerId: number): string {
  const me = match.participants.find((p) => p.player_id === playerId)
  return me ? outcomeLabel(me.outcome) || '—' : '—'
}

export default function PlayerProfilePage() {
  const { playerId } = useParams()
  const id = Number(playerId)
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null)

  const stats = useQuery({
    queryKey: ['playerStats', id],
    queryFn: () => getPlayerStats(id),
    enabled: Number.isFinite(id),
  })

  // Default the game tab to the player's most-played game.
  const games = stats.data?.games_played ?? []
  const activeGameId =
    selectedGameId ??
    (games.length > 0
      ? [...games].sort((a, b) => b.matches_played - a.matches_played)[0].game.id
      : null)

  // Fetch newest-first so prolific players (>100 matches) see their latest
  // matches and current rating trajectory, not the oldest page.
  const history = useQuery({
    queryKey: ['playerMatches', id, activeGameId],
    queryFn: () =>
      getPlayerMatches(id, {
        game_id: activeGameId ?? undefined,
        limit: 100,
        sort_order: 'desc',
      }),
    enabled: Number.isFinite(id) && activeGameId !== null,
  })

  // Rating-over-time series derived from before + change on each match
  // (reversed into chronological order for the chart).
  const chartData = useMemo(() => {
    const matches = [...(history.data?.items ?? [])].reverse()
    const points: { label: string; rating: number }[] = []
    for (const match of matches) {
      const me = match.participants.find((p) => p.player_id === id)
      if (!me?.rating_info_before || !me.rating_info_change) continue
      points.push({
        label: new Date(match.played_at).toLocaleDateString(),
        rating: Math.round(
          me.rating_info_before.rating + me.rating_info_change.rating_change,
        ),
      })
    }
    return points
  }, [history.data, id])

  if (stats.isPending) return <Spinner />
  if (stats.error) return <ErrorNote message={errorMessage(stats.error)} />
  const data = stats.data!

  const recentMatches = (history.data?.items ?? []).slice(0, 15)
  const activeGame = games.find((g) => g.game.id === activeGameId)

  return (
    <div>
      <PageHeader
        title={data.player_name}
        subtitle={`${data.total_matches} matches · ${data.total_wins}W ${data.total_losses}L ${data.total_draws}D · ${(data.overall_win_rate * 100).toFixed(0)}% win rate`}
      />

      {games.length === 0 && (
        <EmptyState
          title="No matches yet"
          hint="This player hasn't been rated in any game."
        />
      )}

      {games.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {games.map((gameStats) => (
              <button
                key={gameStats.game.id}
                onClick={() => setSelectedGameId(gameStats.game.id)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  gameStats.game.id === activeGameId
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                }`}
              >
                {gameStats.game.name}
              </button>
            ))}
          </div>

          {activeGame && (
            <div className="mb-6 grid gap-3 sm:grid-cols-4">
              <Card className="p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Rating
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  {Math.round(activeGame.rating_info.rating)}
                  <span className="ml-2 text-sm font-normal text-slate-500">
                    ± {Math.round(activeGame.rating_info.rd)}
                  </span>
                </p>
              </Card>
              <Card className="p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Matches
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  {activeGame.matches_played}
                </p>
              </Card>
              <Card className="p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Record
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  {activeGame.wins}–{activeGame.losses}
                  {activeGame.draws > 0 && `–${activeGame.draws}`}
                </p>
              </Card>
              <Card className="p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Win rate
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums">
                  {(activeGame.win_rate * 100).toFixed(0)}%
                </p>
              </Card>
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">
                Rating history
              </h2>
              {history.isPending && <Spinner />}
              {chartData.length < 2 ? (
                !history.isPending && (
                  <p className="py-8 text-center text-sm text-slate-500">
                    Need a couple of matches to draw a trend.
                  </p>
                )
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        stroke="#64748b"
                        fontSize={11}
                        tickLine={false}
                      />
                      <YAxis
                        stroke="#64748b"
                        fontSize={11}
                        tickLine={false}
                        domain={['auto', 'auto']}
                        width={45}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: 8,
                          color: '#e2e8f0',
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="rating"
                        stroke="#818cf8"
                        strokeWidth={2}
                        dot={{ r: 2.5, fill: '#818cf8' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-300">
                Recent matches
              </h2>
              {recentMatches.length === 0 && !history.isPending && (
                <p className="py-8 text-center text-sm text-slate-500">
                  No matches for this game.
                </p>
              )}
              <ul className="divide-y divide-slate-800/60">
                {recentMatches.map((match) => {
                  const me = match.participants.find(
                    (p) => p.player_id === id,
                  )
                  const label = playerOutcomeLabel(match, id)
                  return (
                    <li
                      key={match.id}
                      className="flex items-center justify-between gap-2 py-2 text-sm"
                    >
                      <div className="min-w-0">
                        <span
                          className={`mr-2 inline-block w-10 rounded px-1.5 py-0.5 text-center text-xs font-bold uppercase ${
                            label === 'win'
                              ? 'bg-emerald-950/80 text-emerald-400'
                              : label === 'loss'
                                ? 'bg-red-950/80 text-red-400'
                                : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {label === 'win' ? 'W' : label === 'loss' ? 'L' : 'D'}
                        </span>
                        <span className="text-slate-400">
                          {new Date(match.played_at).toLocaleDateString()} · vs{' '}
                          {match.participants
                            .filter((p) => p.player_id !== id)
                            .map((p) => p.player.name)
                            .join(', ') || '—'}
                        </span>
                      </div>
                      {me?.rating_info_change && (
                        <RatingDelta
                          value={me.rating_info_change.rating_change}
                        />
                      )}
                    </li>
                  )
                })}
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
