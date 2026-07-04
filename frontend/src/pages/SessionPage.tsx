import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import {
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  Pill,
  Spinner,
} from '../components/ui'
import {
  createMatch,
  errorMessage,
  generateTeams,
  listPlayers,
} from '../lib/api'
import { useFeature } from '../lib/features'
import { useSelectedGame } from '../lib/GameContext'

interface CourtState {
  /** Two teams of player ids, or null when the court is idle. */
  teams: [number[], number[]] | null
  winProbabilities: number[] | null
  /** Worst matchup beyond 80/20 — flag it to the group. */
  lopsided?: boolean
}

interface SessionState {
  id: string
  name: string
  gameId: number
  teamSize: number
  courts: CourtState[]
  bench: number[]
  gamesPlayed: Record<number, number>
  record: Record<number, { w: number; l: number }>
  matchesRecorded: number
  /** Teammate groups already used tonight — matchmaking avoids repeats. */
  pairings?: number[][]
}

const STORAGE_KEY = 'rankforge.session.v1'

function loadSession(): SessionState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as SessionState) : null
  } catch {
    return null
  }
}

export default function SessionPage() {
  const enabled = useFeature('session_mode')
  const { gameId } = useSelectedGame()
  const queryClient = useQueryClient()

  const [session, setSession] = useState<SessionState | null>(loadSession)
  const [busyCourt, setBusyCourt] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [summary, setSummary] = useState<SessionState | null>(null)

  // Setup form state
  const [name, setName] = useState('')
  const [teamSize, setTeamSize] = useState(2)
  const [courtCount, setCourtCount] = useState(2)
  const [selected, setSelected] = useState<number[]>([])

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = playersData?.items ?? []
  const playerName = (id: number) =>
    players.find((p) => p.id === id)?.name ?? `#${id}`

  useEffect(() => {
    if (session === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  }, [session])

  const perCourt = session ? session.teamSize * 2 : teamSize * 2

  const start = () => {
    if (gameId === null || selected.length < teamSize * 2) return
    setSummary(null)
    setSession({
      id: `session-${Date.now()}`,
      name: name.trim() || `Session ${new Date().toLocaleDateString()}`,
      gameId,
      teamSize,
      courts: Array.from({ length: courtCount }, () => ({
        teams: null,
        winProbabilities: null,
      })),
      bench: selected,
      gamesPlayed: Object.fromEntries(selected.map((id) => [id, 0])),
      record: {},
      matchesRecorded: 0,
    })
  }

  const fillCourt = async (index: number, shuffle = false) => {
    if (!session) return
    setActionError(null)
    setBusyCourt(index)
    try {
      const court = session.courts[index]
      // A shuffle re-rolls the same players; a fill takes the next group
      // from the front of the bench (FIFO fairness).
      const pool = shuffle
        ? court.teams!.flat()
        : session.bench.slice(0, perCourt)
      const response = await generateTeams({
        game_id: session.gameId,
        player_ids: pool,
        team_count: 2,
        num_results: shuffle ? 5 : 1,
        // Tonight's previous pairings rank lower, so partners rotate.
        recent_pairings: (session.pairings ?? []).slice(-16),
      })
      const configs = response.configurations
      if (configs.length === 0) throw new Error('No team configuration found')
      const pick = shuffle
        ? configs[Math.floor(Math.random() * configs.length)]
        : configs[0]
      const teams = pick.teams.map((team) =>
        team.map((member) => member.player.id),
      ) as [number[], number[]]
      setSession((s) =>
        s === null
          ? s
          : {
              ...s,
              bench: shuffle
                ? s.bench
                : s.bench.filter((id) => !pool.includes(id)),
              courts: s.courts.map((c, i) =>
                i === index
                  ? {
                      teams,
                      winProbabilities: pick.win_probabilities,
                      lopsided: pick.lopsided ?? false,
                    }
                  : c,
              ),
            },
      )
    } catch (error) {
      setActionError(errorMessage(error))
    } finally {
      setBusyCourt(null)
    }
  }

  const record = useMutation({
    mutationFn: async ({
      index,
      winner,
    }: {
      index: number
      winner: 1 | 2
    }) => {
      const court = session!.courts[index]
      const [team1, team2] = court.teams!
      await createMatch({
        game_id: session!.gameId,
        match_metadata: {
          session_id: session!.id,
          session_name: session!.name,
        },
        participants: [
          ...team1.map((id) => ({
            player_id: id,
            team_id: 1,
            outcome: { result: winner === 1 ? 'win' : 'loss' } as const,
          })),
          ...team2.map((id) => ({
            player_id: id,
            team_id: 2,
            outcome: { result: winner === 2 ? 'win' : 'loss' } as const,
          })),
        ],
      })
      return { index, winner }
    },
    onSuccess: ({ index, winner }) => {
      setSession((s) => {
        if (s === null) return s
        const court = s.courts[index]
        if (!court.teams) return s
        const [team1, team2] = court.teams
        const winners = winner === 1 ? team1 : team2
        const gamesPlayed = { ...s.gamesPlayed }
        const rec = { ...s.record }
        for (const id of [...team1, ...team2]) {
          gamesPlayed[id] = (gamesPlayed[id] ?? 0) + 1
          const entry = rec[id] ?? { w: 0, l: 0 }
          rec[id] = winners.includes(id)
            ? { ...entry, w: entry.w + 1 }
            : { ...entry, l: entry.l + 1 }
        }
        return {
          ...s,
          courts: s.courts.map((c, i) =>
            i === index ? { teams: null, winProbabilities: null } : c,
          ),
          bench: [...s.bench, ...team1, ...team2],
          gamesPlayed,
          record: rec,
          matchesRecorded: s.matchesRecorded + 1,
          pairings: [...(s.pairings ?? []), team1, team2].slice(-24),
        }
      })
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
      queryClient.invalidateQueries({ queryKey: ['matches'] })
    },
    onError: (error) => setActionError(errorMessage(error)),
  })

  const minGames = session
    ? Math.min(
        ...session.bench.map((id) => session.gamesPlayed[id] ?? 0),
        Infinity,
      )
    : 0

  if (!enabled) {
    return (
      <EmptyState
        title="Session mode is not enabled"
        hint="Set RANKFORGE_FEATURES=session_mode on the backend to turn on the live session runner."
      />
    )
  }

  // ---------- Summary after ending ----------
  if (summary) {
    const rows = Object.entries(summary.gamesPlayed).sort(
      (a, b) =>
        (summary.record[Number(b[0])]?.w ?? 0) -
        (summary.record[Number(a[0])]?.w ?? 0),
    )
    return (
      <div>
        <PageHeader
          title={`${summary.name} — summary`}
          subtitle={`${summary.matchesRecorded} matches recorded`}
        />
        <Card className="max-w-md p-4">
          <ul className="divide-y divide-line/60 text-sm">
            {rows.map(([id, games]) => {
              const rec = summary.record[Number(id)] ?? { w: 0, l: 0 }
              return (
                <li key={id} className="flex justify-between py-2">
                  <span className="font-medium">{playerName(Number(id))}</span>
                  <span className="font-data text-mute">
                    {games} games · {rec.w}–{rec.l}
                  </span>
                </li>
              )
            })}
          </ul>
        </Card>
        <button
          onClick={() => setSummary(null)}
          className="mt-4 rounded bg-ember px-4 py-2 font-semibold text-ember-ink hover:bg-ember-bright"
        >
          New session
        </button>
      </div>
    )
  }

  // ---------- Setup ----------
  if (!session) {
    return (
      <div>
        <PageHeader
          title="Session"
          subtitle="Run a night of play: courts, an up-next queue, fair rotation"
        />
        {gameId === null && (
          <EmptyState
            title="No game selected"
            hint="Pick the game this session is for."
          />
        )}
        {gameId !== null && (
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <Card className="p-4">
              <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wider text-mute">
                Who's playing? ({selected.length} selected)
              </h2>
              {isPending && <Spinner />}
              <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                {players.map((player) => {
                  const active = selected.includes(player.id)
                  return (
                    <button
                      key={player.id}
                      onClick={() =>
                        setSelected((ids) =>
                          active
                            ? ids.filter((id) => id !== player.id)
                            : [...ids, player.id],
                        )
                      }
                      className={`rounded border px-3 py-1.5 text-left text-sm font-medium transition-colors ${
                        active
                          ? 'border-ember bg-ember/10 text-ink'
                          : 'border-line text-mute hover:bg-raised'
                      }`}
                    >
                      {player.name}
                    </button>
                  )
                })}
              </div>
            </Card>
            <Card className="h-fit p-4">
              <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wider text-mute">
                Session setup
              </h2>
              <label className="block font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Name (optional)
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={`Session ${new Date().toLocaleDateString()}`}
                  className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm focus:border-ember focus:outline-none"
                />
              </label>
              <label className="mt-3 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Team size
                <select
                  value={teamSize}
                  onChange={(e) => setTeamSize(Number(e.target.value))}
                  className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm focus:border-ember focus:outline-none"
                >
                  <option value="1">Singles (1v1)</option>
                  <option value="2">Doubles (2v2)</option>
                  <option value="3">3v3</option>
                </select>
              </label>
              <label className="mt-3 block font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Courts
                <select
                  value={courtCount}
                  onChange={(e) => setCourtCount(Number(e.target.value))}
                  className="mt-1 w-full rounded border border-line-strong bg-raised px-3 py-1.5 text-sm focus:border-ember focus:outline-none"
                >
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={start}
                disabled={selected.length < teamSize * 2}
                className="mt-4 w-full rounded bg-ember py-2 font-semibold text-ember-ink hover:bg-ember-bright disabled:opacity-40"
              >
                Start session
              </button>
              {selected.length < teamSize * 2 && (
                <p className="mt-2 text-xs text-faint">
                  Need at least {teamSize * 2} players for one court.
                </p>
              )}
            </Card>
          </div>
        )}
      </div>
    )
  }

  // ---------- Active session ----------
  return (
    <div>
      <PageHeader
        title={session.name}
        subtitle={`${session.matchesRecorded} matches recorded · ${session.bench.length} on the bench`}
        actions={
          <button
            onClick={() => {
              setSummary(session)
              setSession(null)
            }}
            className="rounded bg-raised px-3 py-1.5 text-sm font-medium text-mute hover:bg-line"
          >
            End session
          </button>
        }
      />
      {actionError && <ErrorNote message={actionError} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="grid gap-4 sm:grid-cols-2">
          {session.courts.map((court, index) => (
            <Card key={index} className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wider text-mute">
                  Court {index + 1}
                  {court.teams && court.lopsided && (
                    <Pill tone="warn">lopsided</Pill>
                  )}
                </h3>
                {court.teams && (
                  <button
                    onClick={() => fillCourt(index, true)}
                    disabled={busyCourt !== null}
                    className="text-xs font-medium text-ember hover:text-ember disabled:opacity-50"
                  >
                    Shuffle
                  </button>
                )}
              </div>

              {!court.teams && (
                <button
                  onClick={() => fillCourt(index)}
                  disabled={
                    busyCourt !== null || session.bench.length < perCourt
                  }
                  className="w-full rounded border border-dashed border-line-strong py-6 text-sm font-medium text-mute hover:border-ember hover:text-ember disabled:opacity-40"
                >
                  {busyCourt === index
                    ? 'Balancing teams…'
                    : session.bench.length < perCourt
                      ? `Waiting for players (${session.bench.length}/${perCourt})`
                      : 'Fill from bench'}
                </button>
              )}

              {court.teams && (
                <>
                  {court.teams.map((team, t) => (
                    <div
                      key={t}
                      className="mt-1 flex items-center justify-between rounded bg-raised px-3 py-2"
                    >
                      <span className="text-sm font-medium">
                        {team.map(playerName).join(' & ')}
                      </span>
                      {court.winProbabilities && (
                        <span className="text-xs font-data text-faint">
                          {(court.winProbabilities[t] * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  ))}
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {([1, 2] as const).map((team) => (
                      <button
                        key={team}
                        onClick={() => record.mutate({ index, winner: team })}
                        disabled={record.isPending}
                        className="rounded bg-win/15 py-2 text-xs font-semibold text-win hover:bg-win/25 disabled:opacity-50"
                      >
                        Team {team} won
                      </button>
                    ))}
                  </div>
                </>
              )}
            </Card>
          ))}
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <h3 className="mb-2 font-display text-sm font-semibold uppercase tracking-wider text-mute">
              Up next
            </h3>
            {session.bench.length === 0 && (
              <p className="text-sm text-faint">Everyone is playing.</p>
            )}
            <ol className="space-y-1 text-sm">
              {session.bench.map((id, position) => (
                <li
                  key={id}
                  className="flex items-center justify-between gap-2"
                >
                  <span>
                    <span className="mr-2 inline-block w-5 text-right font-data text-faint">
                      {position + 1}.
                    </span>
                    <span
                      className={
                        (session.gamesPlayed[id] ?? 0) === minGames
                          ? 'font-medium text-warn'
                          : 'font-medium'
                      }
                    >
                      {playerName(id)}
                    </span>
                  </span>
                  <span className="text-xs font-data text-faint">
                    {session.gamesPlayed[id] ?? 0} played
                  </span>
                </li>
              ))}
            </ol>
            {session.bench.length > 0 && (
              <p className="mt-2 text-[11px] text-faint">
                Amber = fewest games (owed court time). Queue is
                first-in-first-out.
              </p>
            )}
          </Card>

          <Card className="p-4">
            <h3 className="mb-2 font-display text-sm font-semibold uppercase tracking-wider text-mute">
              Session record
            </h3>
            <ul className="space-y-1 text-sm">
              {Object.entries(session.gamesPlayed)
                .sort(
                  (a, b) =>
                    (session.record[Number(b[0])]?.w ?? 0) -
                    (session.record[Number(a[0])]?.w ?? 0),
                )
                .map(([id, games]) => {
                  const rec = session.record[Number(id)] ?? { w: 0, l: 0 }
                  return (
                    <li key={id} className="flex justify-between gap-2">
                      <span>{playerName(Number(id))}</span>
                      <span className="font-data text-mute">
                        {rec.w}–{rec.l}{' '}
                        <span className="text-faint">({games})</span>
                      </span>
                    </li>
                  )
                })}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  )
}
