import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import App from './App'
import { GameProvider } from './lib/GameContext'
import GamesPage from './pages/GamesPage'
import LeaderboardPage from './pages/LeaderboardPage'
import MatchesPage from './pages/MatchesPage'
import MatchmakingPage from './pages/MatchmakingPage'
import PlayerProfilePage from './pages/PlayerProfilePage'
import RecordMatchPage from './pages/RecordMatchPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 10_000 },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <LeaderboardPage /> },
      { path: 'record', element: <RecordMatchPage /> },
      { path: 'matchmaking', element: <MatchmakingPage /> },
      { path: 'matches', element: <MatchesPage /> },
      { path: 'games', element: <GamesPage /> },
      { path: 'players/:playerId', element: <PlayerProfilePage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <GameProvider>
        <RouterProvider router={router} />
      </GameProvider>
    </QueryClientProvider>
  </StrictMode>,
)
