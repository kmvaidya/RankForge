import { NavLink, Outlet } from 'react-router-dom'

import { useFeature } from './lib/features'

const links = [
  { to: '/', label: 'Leaderboard' },
  { to: '/record', label: 'Record Match' },
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
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="rounded-md bg-indigo-600 px-2 py-0.5 text-sm font-black tracking-tight">
              RF
            </span>
            <span className="text-lg font-bold tracking-tight">RankForge</span>
          </NavLink>
          <nav className="flex flex-wrap items-center gap-1 text-sm">
            {visibleLinks.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 font-medium transition-colors ${
                    isActive
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
