import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  Avatar,
  Card,
  CardTitle,
  EmptyState,
  ErrorNote,
  Pill,
  RatingDelta,
  SegmentedControl,
  Spinner,
  StatCard,
} from '../components/ui'
import {
  errorMessage,
  getPlayerChemistry,
  getPlayerMatches,
  getPlayerStats,
} from '../lib/api'
import { relativeTime } from '../lib/format'
import { outcomeClass } from '../lib/outcome'
import type { ChemistryEntry } from '../lib/types'

function ChemistryList({
  title,
  entries,
  emptyHint,
}: {
  title: string
  entries: ChemistryEntry[]
  emptyHint: string
}) {
  return (
    <div>
      <h3 className="mb-2 font-display text-xs font-semibold uppercase tracking-wider text-faint">
        {title}
      </h3>
      {entries.length === 0 && (
        <p className="text-sm text-faint">{emptyHint}</p>
      )}
      <ul className="space-y-2">
        {entries.slice(0, 6).map((e) => (
          <li
            key={e.player_id}
            className="text-sm"
            title={`Raw ${(e.win_rate * 100).toFixed(0)}% over ${e.matches} matches; displayed rate is confidence-adjusted`}
          >
            <div className="flex items-center justify-between gap-2">
              <Link
                to={`/players/${e.player_id}`}
                className="flex min-w-0 items-center gap-2 font-medium hover:text-ember"
              >
                <Avatar name={e.player_name} size="sm" />
                <span className="truncate">{e.player_name}</span>
              </Link>
              <span className="shrink-0 font-data text-mute">
                {e.wins}–{e.losses}
                {e.draws > 0 && `–${e.draws}`}{' '}
                <span
                  className={e.shrunk_win_rate >= 0.5 ? 'text-win' : 'text-loss'}
                >
                  {(e.shrunk_win_rate * 100).toFixed(0)}%
                </span>
              </span>
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-raised">
              <div
                className={`h-full rounded-full ${
                  e.shrunk_win_rate >= 0.5 ? 'bg-win/70' : 'bg-loss/70'
                }`}
                style={{ width: `${Math.round(e.shrunk_win_rate * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
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

  const chemistry = useQuery({
    queryKey: ['chemistry', id, activeGameId],
    queryFn: () => getPlayerChemistry(id, activeGameId!),
    enabled: Number.isFinite(id) && activeGameId !== null,
  })

  // Rating-over-time series derived from before + change on each match
  // (reversed into chronological order for the chart). ``band`` is the
  // fog-of-war interval [rating − 2·RD, rating + 2·RD]: the engine's own
  // uncertainty about where the player's true skill sits.
  const chartData = useMemo(() => {
    const matches = [...(history.data?.items ?? [])].reverse()
    const points: { label: string; rating: number; band: [number, number] }[] =
      []
    for (const match of matches) {
      const me = match.participants.find((p) => p.player_id === id)
      if (!me?.rating_info_before || !me.rating_info_change) continue
      const rating =
        me.rating_info_before.rating + me.rating_info_change.rating_change
      const rd = me.rating_info_before.rd + me.rating_info_change.rd_change
      points.push({
        label: new Date(match.played_at).toLocaleDateString(),
        rating: Math.round(rating),
        band: [Math.round(rating - 2 * rd), Math.round(rating + 2 * rd)],
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
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <Avatar name={data.player_name} size="lg" />
        <div>
          <h1 className="font-display text-3xl font-bold uppercase tracking-wide">
            {data.player_name}
          </h1>
          <p className="mt-0.5 text-sm text-mute">
            Across all games:{' '}
            <span className="font-data">
              {data.total_matches} matches · {data.total_wins}W{' '}
              {data.total_losses}L {data.total_draws}D ·{' '}
              {(data.overall_win_rate * 100).toFixed(0)}%
            </span>
          </p>
        </div>
      </div>

      {games.length === 0 && (
        <EmptyState
          title="No matches yet"
          hint="This player hasn't been rated in any game."
        />
      )}

      {games.length > 0 && (
        <>
          <div className="mb-4">
            <SegmentedControl
              options={games.map((gameStats) => ({
                value: gameStats.game.id,
                label: gameStats.game.name,
              }))}
              value={activeGameId ?? games[0].game.id}
              onChange={setSelectedGameId}
            />
          </div>

          {activeGame && (
            <div className="mb-6 grid gap-3 sm:grid-cols-4">
              <StatCard
                label="Rating"
                value={Math.round(activeGame.rating_info.rating)}
                caption={`± ${Math.round(activeGame.rating_info.rd)} RD`}
              />
              <StatCard label="Matches" value={activeGame.matches_played} />
              <StatCard
                label="Record"
                value={
                  <>
                    {activeGame.wins}–{activeGame.losses}
                    {activeGame.draws > 0 && `–${activeGame.draws}`}
                  </>
                }
              />
              <StatCard
                label="Win rate"
                value={`${(activeGame.win_rate * 100).toFixed(0)}%`}
              />
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-4">
              <CardTitle className="mb-3">Rating history</CardTitle>
              {history.isPending && <Spinner />}
              {chartData.length < 2 ? (
                !history.isPending && (
                  <p className="py-8 text-center text-sm text-faint">
                    Need a couple of matches to draw a trend.
                  </p>
                )
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData}>
                      <CartesianGrid stroke="#262b31" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        stroke="#71787f"
                        fontSize={11}
                        tickLine={false}
                      />
                      <YAxis
                        stroke="#71787f"
                        fontSize={11}
                        tickLine={false}
                        domain={['auto', 'auto']}
                        width={45}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#131518',
                          border: '1px solid #3a4149',
                          borderRadius: 8,
                          color: '#f2f3f5',
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="band"
                        stroke="none"
                        fill="#ff6a3d"
                        fillOpacity={0.09}
                        activeDot={false}
                        name="rating ± 2·RD"
                      />
                      <Line
                        type="monotone"
                        dataKey="rating"
                        stroke="#ff6a3d"
                        strokeWidth={2}
                        dot={{ r: 2.5, fill: '#ff6a3d' }}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            <Card className="p-4">
              <CardTitle className="mb-3">Recent matches</CardTitle>
              {recentMatches.length === 0 && !history.isPending && (
                <p className="py-8 text-center text-sm text-faint">
                  No matches for this game.
                </p>
              )}
              <ul className="divide-y divide-line/60">
                {recentMatches.map((match) => {
                  const me = match.participants.find(
                    (p) => p.player_id === id,
                  )
                  const klass = me ? outcomeClass(me.outcome) : null
                  return (
                    <li
                      key={match.id}
                      className="flex items-center justify-between gap-2 py-2 text-sm"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <Pill
                          tone={
                            klass === 'win'
                              ? 'win'
                              : klass === 'loss'
                                ? 'loss'
                                : 'draw'
                          }
                        >
                          {me && 'rank' in me.outcome
                            ? `#${me.outcome.rank}`
                            : (klass ?? '—')}
                        </Pill>
                        <span className="truncate text-mute">
                          {relativeTime(match.played_at)} · vs{' '}
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

          {chemistry.data &&
            (chemistry.data.partners.length > 0 ||
              chemistry.data.rivals.length > 0) && (
              <Card className="mt-6 p-4">
                <CardTitle className="mb-3">
                  Partners &amp; head-to-head
                  {activeGame && (
                    <span className="ml-2 normal-case tracking-normal text-faint">
                      {activeGame.game.name}
                    </span>
                  )}
                </CardTitle>
                <div className="grid gap-6 sm:grid-cols-2">
                  <ChemistryList
                    title="Best partners (record together)"
                    entries={chemistry.data.partners}
                    emptyHint="No team matches yet."
                  />
                  <ChemistryList
                    title="Head-to-head (record against)"
                    entries={chemistry.data.rivals}
                    emptyHint="No opponents yet."
                  />
                </div>
                <p className="mt-3 text-xs text-faint">
                  Rates are confidence-adjusted: small samples are pulled
                  toward the overall mean, so a 2–0 pairing doesn't read as an
                  unbeatable 100%. Hover a row for the raw rate.
                </p>
              </Card>
            )}
        </>
      )}
    </div>
  )
}
