import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'

import { listGames } from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'

/** Global game switcher in the app header, bound to shared context. */
export default function GamePicker() {
  const { gameId, setGameId } = useSelectedGame()
  const { data } = useQuery({ queryKey: ['games'], queryFn: listGames })
  const games = useMemo(() => data?.items ?? [], [data])

  // Auto-select the first game once games load and nothing is selected.
  useEffect(() => {
    if (games.length === 0) return
    if (gameId === null || !games.some((g) => g.id === gameId)) {
      setGameId(games[0].id)
    }
  }, [games, gameId, setGameId])

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="font-display text-xs font-semibold uppercase tracking-wider text-faint">
        Game
      </span>
      <select
        value={gameId ?? ''}
        onChange={(e) => setGameId(e.target.value ? Number(e.target.value) : null)}
        className="rounded border border-line bg-raised px-2.5 py-1.5 text-sm font-medium text-ink focus:border-ember focus:outline-none focus-visible:ring-2 focus-visible:ring-ember/60"
      >
        {games.length === 0 && <option value="">No games yet</option>}
        {games.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </select>
    </label>
  )
}
