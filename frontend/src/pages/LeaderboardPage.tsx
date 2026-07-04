import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import GamePicker from '../components/GamePicker'
import { Card, EmptyState, ErrorNote, PageHeader, Spinner } from '../components/ui'
import {
  errorMessage,
  getGameHealth,
  getLeaderboard,
  listMatches,
} from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'
import type { LeaderboardEntry } from '../lib/types'

type SortKey = 'rank' | 'rating' | 'rd' | 'wins' | 'matches' | 'winRate'
type MinFilter = 'auto' | 'off' | number
type DisplayMode = 'rating' | 'conservative'

/** The rating a row is ranked and displayed by. Conservative mode uses the
 *  Glicko lower bound (rating − 2·RD): unproven players rank low until
 *  their uncertainty shrinks. */
function displayedRating(entry: LeaderboardEntry, mode: DisplayMode): number {
  return mode === 'conservative'
    ? entry.rating_info.rating - 2 * entry.rating_info.rd
    : entry.rating_info.rating
}

function statNumber(entry: LeaderboardEntry, key: string): number {
  const value = entry.stats?.[key]
  return typeof value === 'number' ? value : 0
}

/** Auto threshold: 5% of the game's matches, between 1 and 10.
 *  Glicko-2 ratings are provisional at low sample sizes, but a small
 *  activity (e.g. 12 matches total) shouldn't demand 10 games. */
function autoThreshold(totalMatches: number): number {
  return Math.min(10, Math.max(1, Math.ceil(totalMatches * 0.05)))
}

export default function LeaderboardPage() {
  const { gameId } = useSelectedGame()
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [descending, setDescending] = useState(false)
  const [minFilter, setMinFilter] = useState<MinFilter>('auto')
  const [displayMode, setDisplayMode] = useState<DisplayMode>('rating')

  const { data, isPending, error } = useQuery({
    queryKey: ['leaderboard', gameId],
    queryFn: () => getLeaderboard(gameId!),
    enabled: gameId !== null,
  })

  const { data: health } = useQuery({
    queryKey: ['gameHealth', gameId],
    queryFn: () => getGameHealth(gameId!),
    enabled: gameId !== null,
  })

  // Total matches in this game — drives the "Auto" minimum-matches threshold.
  const { data: matchTotals } = useQuery({
    queryKey: ['matchTotal', gameId],
    queryFn: () => listMatches({ game_id: gameId!, limit: 1 }),
    enabled: gameId !== null,
  })

  const threshold =
    minFilter === 'off'
      ? 0
      : minFilter === 'auto'
        ? autoThreshold(matchTotals?.total ?? 0)
        : minFilter

  const { rows, hiddenCount } = useMemo(() => {
    const items = data?.items ?? []
    const eligible = items.filter(
      (e) => statNumber(e, 'matches_played') >= threshold,
    )
    // Re-rank the visible board so it reads 1..n by the displayed rating.
    const reranked = [...eligible]
      .sort(
        (a, b) =>
          displayedRating(b, displayMode) - displayedRating(a, displayMode),
      )
      .map((e, i) => ({ ...e, rank: i + 1 }))
    const value = (e: LeaderboardEntry): number => {
      switch (sortKey) {
        case 'rank':
          return e.rank
        case 'rating':
          return displayedRating(e, displayMode)
        case 'rd':
          return e.rating_info.rd
        case 'wins':
          return statNumber(e, 'wins')
        case 'matches':
          return statNumber(e, 'matches_played')
        case 'winRate':
          return statNumber(e, 'win_rate')
      }
    }
    const sorted = reranked.sort((a, b) =>
      descending ? value(b) - value(a) : value(a) - value(b),
    )
    return { rows: sorted, hiddenCount: items.length - eligible.length }
  }, [data, sortKey, descending, threshold, displayMode])

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDescending(!descending)
    else {
      setSortKey(key)
      // ranks read best ascending, everything else descending
      setDescending(key !== 'rank')
    }
  }

  const header = (label: string, key: SortKey, align = 'text-right') => (
    <th
      className={`cursor-pointer select-none px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-200 ${align}`}
      onClick={() => toggleSort(key)}
    >
      {label}
      {sortKey === key && (descending ? ' ↓' : ' ↑')}
    </th>
  )

  return (
    <div>
      <PageHeader
        title="Leaderboard"
        subtitle="Players ranked by Glicko-2 rating"
        actions={
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-slate-400">Display</span>
              <select
                value={displayMode}
                onChange={(e) => setDisplayMode(e.target.value as DisplayMode)}
                className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 font-medium focus:border-indigo-500 focus:outline-none"
              >
                <option value="rating">Rating</option>
                <option value="conservative">Conservative (R−2·RD)</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-slate-400">Min matches</span>
              <select
                value={typeof minFilter === 'number' ? String(minFilter) : minFilter}
                onChange={(e) => {
                  const v = e.target.value
                  setMinFilter(v === 'auto' || v === 'off' ? v : Number(v))
                }}
                className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 font-medium focus:border-indigo-500 focus:outline-none"
              >
                <option value="auto">Auto ({autoThreshold(matchTotals?.total ?? 0)})</option>
                <option value="off">Off</option>
                <option value="5">5</option>
                <option value="10">10</option>
                <option value="25">25</option>
              </select>
            </label>
            <GamePicker />
          </div>
        }
      />

      {error && <ErrorNote message={errorMessage(error)} />}
      {gameId === null && (
        <EmptyState
          title="No game selected"
          hint="Create a game on the Games page to get started."
        />
      )}
      {gameId !== null && isPending && <Spinner />}

      {data && rows.length === 0 && (
        <EmptyState
          title={
            hiddenCount > 0 ? 'No players meet the filter' : 'No rated players yet'
          }
          hint={
            hiddenCount > 0
              ? `All ${hiddenCount} player(s) have fewer than ${threshold} matches. Lower the minimum or set it to Off.`
              : 'Record a match to put players on the board.'
          }
        />
      )}

      {rows.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="border-b border-slate-800">
              <tr>
                {header('#', 'rank', 'text-left')}
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Player
                </th>
                {header('Rating', 'rating')}
                {header('± RD', 'rd')}
                {header('Matches', 'matches')}
                {header('Wins', 'wins')}
                {header('Win %', 'winRate')}
              </tr>
            </thead>
            <tbody>
              {rows.map((entry) => (
                <tr
                  key={entry.player.id}
                  className="border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30"
                >
                  <td className="px-3 py-2.5 font-semibold tabular-nums text-slate-400">
                    {entry.rank}
                  </td>
                  <td className="px-3 py-2.5">
                    <Link
                      to={`/players/${entry.player.id}`}
                      className="font-medium text-indigo-300 hover:text-indigo-200 hover:underline"
                    >
                      {entry.player.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-right font-bold tabular-nums">
                    {Math.round(displayedRating(entry, displayMode))}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-400">
                    {Math.round(entry.rating_info.rd)}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {statNumber(entry, 'matches_played')}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {statNumber(entry, 'wins')}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {(statNumber(entry, 'win_rate') * 100).toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {displayMode === 'conservative' && (
            <p className="px-3 pt-3 text-xs text-slate-500">
              Conservative display: each rating is its Glicko lower bound
              (rating − 2·RD) — a player must play enough to shrink their
              uncertainty before ranking high.
            </p>
          )}
          {hiddenCount > 0 && (
            <p className="px-3 pt-3 text-xs text-slate-500">
              {hiddenCount} provisional player{hiddenCount === 1 ? '' : 's'}{' '}
              hidden (fewer than {threshold}{' '}
              {threshold === 1 ? 'match' : 'matches'}) — Glicko-2 ratings are
              unreliable at low sample sizes. Set the filter to Off to show
              everyone.
            </p>
          )}
          {health && (
            <p className="px-3 pt-2 text-xs text-slate-600">
              League health: mean rating{' '}
              <span className="tabular-nums">
                {Math.round(health.mean_rating)}
              </span>{' '}
              · drift{' '}
              <span className="tabular-nums">
                {health.rating_drift.toFixed(0)}
              </span>{' '}
              from 1500 · {health.players} rated players ·{' '}
              {health.matches} matches
            </p>
          )}
        </Card>
      )}
    </div>
  )
}
