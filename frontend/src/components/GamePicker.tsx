import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'

import { listGames } from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'

/** Game dropdown bound to the shared selected-game context. */
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
      <span className="text-slate-400">Game</span>
      <select
        value={gameId ?? ''}
        onChange={(e) => setGameId(e.target.value ? Number(e.target.value) : null)}
        className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 font-medium focus:border-indigo-500 focus:outline-none"
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
