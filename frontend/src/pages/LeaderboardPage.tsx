import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import GamePicker from '../components/GamePicker'
import { Card, EmptyState, ErrorNote, PageHeader, Spinner } from '../components/ui'
import { errorMessage, getLeaderboard } from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'
import type { LeaderboardEntry } from '../lib/types'

type SortKey = 'rank' | 'rating' | 'rd' | 'wins' | 'matches' | 'winRate'

function statNumber(entry: LeaderboardEntry, key: string): number {
  const value = entry.stats?.[key]
  return typeof value === 'number' ? value : 0
}

export default function LeaderboardPage() {
  const { gameId } = useSelectedGame()
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [descending, setDescending] = useState(false)

  const { data, isPending, error } = useQuery({
    queryKey: ['leaderboard', gameId],
    queryFn: () => getLeaderboard(gameId!),
    enabled: gameId !== null,
  })

  const rows = useMemo(() => {
    const items = data?.items ?? []
    const value = (e: LeaderboardEntry): number => {
      switch (sortKey) {
        case 'rank':
          return e.rank
        case 'rating':
          return e.rating_info.rating
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
    return [...items].sort((a, b) =>
      descending ? value(b) - value(a) : value(a) - value(b),
    )
  }, [data, sortKey, descending])

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
        actions={<GamePicker />}
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
          title="No rated players yet"
          hint="Record a match to put players on the board."
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
                    {Math.round(entry.rating_info.rating)}
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
        </Card>
      )}
    </div>
  )
}
