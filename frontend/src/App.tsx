import { NavLink, Outlet } from 'react-router-dom'

import GamePicker from './components/GamePicker'
import { useFeature } from './lib/features'

const links = [
  { to: '/', label: 'Leaderboard' },
  { to: '/record', label: 'Record' },
  { to: '/session', label: 'Session', feature: 'session_mode' },
  { to: '/matchmaking', label: 'Matchmaking' },
  { to: '/matches', label: 'Matches' },
  { to: '/games', label: 'Games' },
]

export default function App() {
  const sessionMode = useFeature('session_mode')
  const visibleLinks = links.filter(
    (link) => !link.feature || (link.feature === 'session_mode' && sessionMode),
  )
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink
            to="/"
            className="font-display text-xl font-bold uppercase tracking-wide"
          >
            Rank<span className="text-ember">forge</span>
          </NavLink>
          <nav className="flex flex-wrap items-center gap-1">
            {visibleLinks.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `rounded px-2.5 py-1.5 font-display text-sm font-semibold uppercase tracking-wider transition-colors ${
                    isActive
                      ? 'text-ember'
                      : 'text-mute hover:bg-raised hover:text-ink'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          {/* The selected game is app-level context: every page except the
              player profile is scoped to it. */}
          <div className="ml-auto">
            <GamePicker />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
