import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

/** Remembers which game the user is working with across pages. */
interface GameContextValue {
  gameId: number | null
  setGameId: (id: number | null) => void
}

const GameContext = createContext<GameContextValue>({
  gameId: null,
  setGameId: () => {},
})

const STORAGE_KEY = 'rankforge.selectedGameId'

export function GameProvider({ children }: { children: ReactNode }) {
  const [gameId, setGameId] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? Number(stored) : null
  })

  useEffect(() => {
    if (gameId === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(gameId))
  }, [gameId])

  return (
    <GameContext.Provider value={{ gameId, setGameId }}>
      {children}
    </GameContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSelectedGame() {
  return useContext(GameContext)
}
