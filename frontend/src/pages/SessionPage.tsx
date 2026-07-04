import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import {
  Avatar,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Pill,
  PlayerChip,
  SegmentedControl,
  Select,
  Spinner,
} from '../components/ui'
import {
  createMatch,
  errorMessage,
  generateTeams,
  listPlayers,
  predictMatch,
} from '../lib/api'
import { useFeature } from '../lib/features'
import { useSelectedGame } from '../lib/GameContext'
import type { ParticipantCreate } from '../lib/types'

interface StationState {
  /** Teams of player ids, or null when the station is idle. */
  teams: number[][] | null
  winProbabilities: number[] | null
  /** Worst matchup beyond 80/20 — flag it to the group. */
  lopsided?: boolean
}

interface SessionState {
  v: 2
  id: string
  name: string
  gameId: number
  /** What the group calls a playing area: Court, Table, Board, Station. */
  noun: string
  /** Free-for-all: every player is their own team, finish is ranked. */
  ffa: boolean
  /** Teams per station (team format). */
  teamCount: number
  /** Players per team (team format). */
  teamSize: number
  /** Players per station (free-for-all format). */
  ffaSize: number
  stations: StationState[]
  bench: number[]
  gamesPlayed: Record<number, number>
  record: Record<number, { w: number; l: number; d: number }>
  matchesRecorded: number
  /** Teammate groups already used tonight — matchmaking avoids repeats. */
  pairings?: number[][]
}

const STORAGE_KEY = 'rankforge.session.v2'
const LEGACY_KEY = 'rankforge.session.v1'
const NOUNS = ['Court', 'Table', 'Board', 'Station']

function loadSession(): SessionState | null {
  try {
    // v1 sessions predate formats/nouns; a night's session is ephemeral,
    // so discard rather than migrate.
    localStorage.removeItem(LEGACY_KEY)
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as SessionState
    return parsed.v === 2 ? parsed : null
  } catch {
    return null
  }
}

type TeamResult = 'w' | 'l' | 'd'

export default function SessionPage() {
  const enabled = useFeature('session_mode')
  const { gameId } = useSelectedGame()
  const queryClient = useQueryClient()

  const [session, setSession] = useState<SessionState | null>(loadSession)
  const [busyStation, setBusyStation] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [summary, setSummary] = useState<SessionState | null>(null)
  /** Ranked stations: station index → team indices tapped in finish order. */
  const [placing, setPlacing] = useState<Record<number, number[]>>({})

  // Setup form state
  const [name, setName] = useState('')
  const [noun, setNoun] = useState('Court')
  const [ffa, setFfa] = useState(false)
  const [teamCount, setTeamCount] = useState(2)
  const [teamSize, setTeamSize] = useState(2)
  const [ffaSize, setFfaSize] = useState(4)
  const [stationCount, setStationCount] = useState(2)
  const [selected, setSelected] = useState<number[]>([])

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = useMemo(() => playersData?.items ?? [], [playersData])
  const playerName = (id: number) =>
    players.find((p) => p.id === id)?.name ?? `#${id}`

  useEffect(() => {
    if (session === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  }, [session])

  const perStation = session
    ? session.ffa
      ? session.ffaSize
      : session.teamCount * session.teamSize
    : ffa
      ? ffaSize
      : teamCount * teamSize

  /** Ranked finish applies to free-for-alls and 3+-team stations. */
  const rankedSession = session ? session.ffa || session.teamCount > 2 : false

  const start = () => {
    if (gameId === null || selected.length < perStation) return
    setSummary(null)
    setPlacing({})
    setSession({
      v: 2,
      id: `session-${Date.now()}`,
      name: name.trim() || `Session ${new Date().toLocaleDateString()}`,
      gameId,
      noun,
      ffa,
      teamCount,
      teamSize,
      ffaSize,
      stations: Array.from({ length: stationCount }, () => ({
        teams: null,
        winProbabilities: null,
      })),
      bench: selected,
      gamesPlayed: Object.fromEntries(selected.map((id) => [id, 0])),
      record: {},
      matchesRecorded: 0,
    })
  }

  const fillStation = async (index: number, shuffle = false) => {
    if (!session) return
    setActionError(null)
    setBusyStation(index)
    try {
      const station = session.stations[index]
      // A shuffle re-rolls the same players; a fill takes the next group
      // from the front of the bench (FIFO fairness).
      const pool = shuffle
        ? station.teams!.flat()
        : session.bench.slice(0, perStation)

      let teams: number[][]
      let winProbabilities: number[] | null
      let lopsided = false
      if (session.ffa) {
        // Everyone plays everyone — no composition to optimize, but the
        // rating engine still prices each player's chance of winning.
        teams = pool.map((id) => [id])
        try {
          const odds = await predictMatch(session.gameId, teams)
          winProbabilities = odds.teams.map((t) => t.win_probability)
          lopsided = odds.lopsided
        } catch {
          winProbabilities = null
        }
      } else {
        const response = await generateTeams({
          game_id: session.gameId,
          player_ids: pool,
          team_count: session.teamCount,
          num_results: shuffle ? 5 : 1,
          // Tonight's previous pairings rank lower, so partners rotate.
          recent_pairings: (session.pairings ?? []).slice(-16),
        })
        const configs = response.configurations
        if (configs.length === 0) throw new Error('No team configuration found')
        const pick = shuffle
          ? configs[Math.floor(Math.random() * configs.length)]
          : configs[0]
        teams = pick.teams.map((team) => team.map((m) => m.player.id))
        winProbabilities = pick.win_probabilities
        lopsided = pick.lopsided ?? false
      }

      setPlacing((p) => ({ ...p, [index]: [] }))
      setSession((s) =>
        s === null
          ? s
          : {
              ...s,
              bench: shuffle
                ? s.bench
                : s.bench.filter((id) => !pool.includes(id)),
              stations: s.stations.map((c, i) =>
                i === index ? { teams, winProbabilities, lopsided } : c,
              ),
            },
      )
    } catch (error) {
      setActionError(errorMessage(error))
    } finally {
      setBusyStation(null)
    }
  }

  const record = useMutation({
    mutationFn: async ({
      participants,
    }: {
      index: number
      participants: ParticipantCreate[]
      results: TeamResult[]
    }) => {
      await createMatch({
        game_id: session!.gameId,
        match_metadata: {
          session_id: session!.id,
          session_name: session!.name,
        },
        participants,
      })
    },
    onSuccess: (_, { index, results }) => {
      setPlacing((p) => {
        const next = { ...p }
        delete next[index]
        return next
      })
      setSession((s) => {
        if (s === null) return s
        const station = s.stations[index]
        if (!station.teams) return s
        const teams = station.teams
        const gamesPlayed = { ...s.gamesPlayed }
        const rec = { ...s.record }
        teams.forEach((team, teamIndex) => {
          for (const id of team) {
            gamesPlayed[id] = (gamesPlayed[id] ?? 0) + 1
            const entry = rec[id] ?? { w: 0, l: 0, d: 0 }
            const result = results[teamIndex]
            rec[id] = {
              ...entry,
              w: entry.w + (result === 'w' ? 1 : 0),
              l: entry.l + (result === 'l' ? 1 : 0),
              d: entry.d + (result === 'd' ? 1 : 0),
            }
          }
        })
        const newPairings =
          !s.ffa && s.teamSize > 1
            ? [...(s.pairings ?? []), ...teams].slice(-24)
            : s.pairings
        return {
          ...s,
          stations: s.stations.map((c, i) =>
            i === index ? { teams: null, winProbabilities: null } : c,
          ),
          bench: [...s.bench, ...teams.flat()],
          gamesPlayed,
          record: rec,
          matchesRecorded: s.matchesRecorded + 1,
          pairings: newPairings,
        }
      })
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
      queryClient.invalidateQueries({ queryKey: ['matches'] })
    },
    onError: (error) => setActionError(errorMessage(error)),
  })

  /** Two-team stations: one tap on the winner (or a draw). */
  const recordBinary = (index: number, winner: 1 | 2 | 'draw') => {
    const teams = session?.stations[index]?.teams
    if (!teams || teams.length !== 2) return
    const results: TeamResult[] =
      winner === 'draw' ? ['d', 'd'] : winner === 1 ? ['w', 'l'] : ['l', 'w']
    const participants: ParticipantCreate[] = teams.flatMap(
      (team, teamIndex) =>
        team.map((id) => ({
          player_id: id,
          team_id: teamIndex + 1,
          outcome: {
            result:
              results[teamIndex] === 'd'
                ? ('draw' as const)
                : results[teamIndex] === 'w'
                  ? ('win' as const)
                  : ('loss' as const),
          },
        })),
    )
    record.mutate({ index, participants, results })
  }

  /** Ranked stations: submit once every team has been tapped in order. */
  const recordRanked = (index: number) => {
    const teams = session?.stations[index]?.teams
    const order = placing[index]
    if (!teams || !order || order.length !== teams.length) return
    const rankOf = (teamIndex: number) => order.indexOf(teamIndex) + 1
    const participants: ParticipantCreate[] = teams.flatMap(
      (team, teamIndex) =>
        team.map((id) => ({
          player_id: id,
          team_id: teamIndex + 1,
          outcome: { rank: rankOf(teamIndex) },
        })),
    )
    const results: TeamResult[] = teams.map((_, teamIndex) =>
      rankOf(teamIndex) === 1 ? 'w' : 'l',
    )
    record.mutate({ index, participants, results })
  }

  const tapPlace = (stationIndex: number, teamIndex: number) => {
    setPlacing((p) => {
      const order = p[stationIndex] ?? []
      if (order.includes(teamIndex)) return p
      return { ...p, [stationIndex]: [...order, teamIndex] }
    })
  }

  const minGames = session
    ? Math.min(...session.bench.map((id) => session.gamesPlayed[id] ?? 0), Infinity)
    : 0

  const teamLabel = (teams: number[][], teamIndex: number) =>
    teams[teamIndex].length === 1
      ? playerName(teams[teamIndex][0])
      : `Team ${teamIndex + 1}`

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
              const rec = summary.record[Number(id)] ?? { w: 0, l: 0, d: 0 }
              return (
                <li key={id} className="flex items-center justify-between py-2">
                  <span className="flex items-center gap-2 font-medium">
                    <Avatar name={playerName(Number(id))} size="sm" />
                    {playerName(Number(id))}
                  </span>
                  <span className="font-data text-mute">
                    {games} games · {rec.w}–{rec.l}
                    {rec.d > 0 && `–${rec.d}`}
                  </span>
                </li>
              )
            })}
          </ul>
        </Card>
        <Button
          variant="primary"
          onClick={() => setSummary(null)}
          className="mt-4"
        >
          New session
        </Button>
      </div>
    )
  }

  // ---------- Setup ----------
  if (!session) {
    return (
      <div>
        <PageHeader
          title="Session"
          subtitle="Run a night of play: fair fills, an up-next queue, one-tap results"
        />
        {gameId === null && (
          <EmptyState
            title="No game selected"
            hint="Pick the game this session is for."
          />
        )}
        {gameId !== null && (
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <Card className="p-4">
              <CardTitle className="mb-3">
                Who's playing? ({selected.length} selected)
              </CardTitle>
              {isPending && <Spinner />}
              <div className="flex flex-wrap gap-1.5">
                {players.map((player) => (
                  <PlayerChip
                    key={player.id}
                    name={player.name}
                    active={selected.includes(player.id)}
                    onClick={() =>
                      setSelected((ids) =>
                        ids.includes(player.id)
                          ? ids.filter((id) => id !== player.id)
                          : [...ids, player.id],
                      )
                    }
                  />
                ))}
              </div>
            </Card>
            <Card className="h-fit p-4">
              <CardTitle className="mb-3">Session setup</CardTitle>
              <Field label="Name (optional)">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={`Session ${new Date().toLocaleDateString()}`}
                />
              </Field>

              <Field label="Format" className="mt-3">
                <SegmentedControl
                  options={[
                    { value: 'teams', label: 'Teams' },
                    { value: 'ffa', label: 'Free-for-all' },
                  ]}
                  value={ffa ? 'ffa' : 'teams'}
                  onChange={(v) => setFfa(v === 'ffa')}
                />
              </Field>

              {!ffa && (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <Field label="Teams">
                    <SegmentedControl
                      size="sm"
                      options={[2, 3, 4].map((n) => ({ value: n, label: n }))}
                      value={teamCount}
                      onChange={setTeamCount}
                    />
                  </Field>
                  <Field label="Team size">
                    <SegmentedControl
                      size="sm"
                      options={[1, 2, 3, 4].map((n) => ({
                        value: n,
                        label: n,
                      }))}
                      value={teamSize}
                      onChange={setTeamSize}
                    />
                  </Field>
                </div>
              )}
              {ffa && (
                <Field label="Players per station" className="mt-3">
                  <Select
                    value={ffaSize}
                    onChange={(e) => setFfaSize(Number(e.target.value))}
                  >
                    {[2, 3, 4, 5, 6, 7, 8].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}

              <div className="mt-3 grid grid-cols-2 gap-3">
                <Field label="Playing areas">
                  <Select
                    value={stationCount}
                    onChange={(e) => setStationCount(Number(e.target.value))}
                  >
                    {[1, 2, 3, 4, 5, 6].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Call them">
                  <Select value={noun} onChange={(e) => setNoun(e.target.value)}>
                    {NOUNS.map((n) => (
                      <option key={n} value={n}>
                        {n}s
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>

              <Button
                variant="primary"
                onClick={start}
                disabled={selected.length < perStation}
                className="mt-4 w-full"
              >
                Start session
              </Button>
              {selected.length < perStation && (
                <p className="mt-2 text-xs text-faint">
                  Need at least {perStation} players for one{' '}
                  {noun.toLowerCase()}.
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
          <Button
            onClick={() => {
              setSummary(session)
              setSession(null)
            }}
          >
            End session
          </Button>
        }
      />
      {actionError && <ErrorNote message={actionError} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="grid gap-4 sm:grid-cols-2">
          {session.stations.map((station, index) => {
            const order = placing[index] ?? []
            return (
              <Card key={index} className="p-4">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-wider text-mute">
                    {session.noun} {index + 1}
                    {station.teams && station.lopsided && (
                      <Pill tone="warn">lopsided</Pill>
                    )}
                  </h3>
                  {station.teams && !session.ffa && (
                    <button
                      onClick={() => fillStation(index, true)}
                      disabled={busyStation !== null}
                      className="text-xs font-medium text-ember hover:text-ember-bright disabled:opacity-50"
                    >
                      Shuffle
                    </button>
                  )}
                </div>

                {!station.teams && (
                  <button
                    onClick={() => fillStation(index)}
                    disabled={
                      busyStation !== null || session.bench.length < perStation
                    }
                    className="w-full rounded-lg border border-dashed border-line-strong py-6 text-sm font-medium text-mute hover:border-ember/60 hover:text-ember disabled:opacity-40"
                  >
                    {busyStation === index
                      ? 'Balancing teams…'
                      : session.bench.length < perStation
                        ? `Waiting for players (${session.bench.length}/${perStation})`
                        : 'Fill from bench'}
                  </button>
                )}

                {station.teams && (
                  <>
                    {station.teams.map((team, t) => {
                      const placed = order.indexOf(t)
                      return (
                        <div
                          key={t}
                          role={rankedSession ? 'button' : undefined}
                          tabIndex={rankedSession ? 0 : undefined}
                          onClick={
                            rankedSession ? () => tapPlace(index, t) : undefined
                          }
                          onKeyDown={
                            rankedSession
                              ? (e) => {
                                  if (e.key === 'Enter') tapPlace(index, t)
                                }
                              : undefined
                          }
                          className={`mt-1 flex items-center justify-between rounded px-3 py-2 ${
                            rankedSession
                              ? 'cursor-pointer bg-raised hover:bg-line'
                              : 'bg-raised'
                          } ${placed === 0 ? 'ring-1 ring-win/50' : ''}`}
                        >
                          <span className="flex items-center gap-2 text-sm font-medium">
                            {rankedSession && (
                              <span
                                className={`inline-flex h-5 w-5 items-center justify-center rounded-full font-data text-[11px] font-semibold ${
                                  placed >= 0
                                    ? 'bg-ember text-ember-ink'
                                    : 'bg-surface text-faint'
                                }`}
                              >
                                {placed >= 0 ? placed + 1 : '·'}
                              </span>
                            )}
                            {team.map(playerName).join(' & ')}
                          </span>
                          {station.winProbabilities && (
                            <span className="font-data text-xs text-faint">
                              {(station.winProbabilities[t] * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      )
                    })}

                    {!rankedSession && (
                      <div className="mt-3 grid grid-cols-3 gap-2">
                        <button
                          onClick={() => recordBinary(index, 1)}
                          disabled={record.isPending}
                          className="rounded bg-win/15 py-2 text-xs font-semibold text-win hover:bg-win/25 disabled:opacity-50"
                        >
                          {teamLabel(station.teams, 0)} won
                        </button>
                        <button
                          onClick={() => recordBinary(index, 'draw')}
                          disabled={record.isPending}
                          className="rounded bg-raised py-2 text-xs font-semibold text-mute hover:bg-line disabled:opacity-50"
                        >
                          Draw
                        </button>
                        <button
                          onClick={() => recordBinary(index, 2)}
                          disabled={record.isPending}
                          className="rounded bg-win/15 py-2 text-xs font-semibold text-win hover:bg-win/25 disabled:opacity-50"
                        >
                          {teamLabel(station.teams, 1)} won
                        </button>
                      </div>
                    )}

                    {rankedSession && (
                      <div className="mt-3 flex items-center gap-2">
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => recordRanked(index)}
                          disabled={
                            record.isPending ||
                            order.length !== station.teams.length
                          }
                          className="flex-1"
                        >
                          {order.length === station.teams.length
                            ? 'Record finish'
                            : `Tap in finishing order (${order.length}/${station.teams.length})`}
                        </Button>
                        {order.length > 0 && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setPlacing((p) => ({ ...p, [index]: [] }))
                            }
                          >
                            Clear
                          </Button>
                        )}
                      </div>
                    )}
                  </>
                )}
              </Card>
            )
          })}
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <CardTitle className="mb-2">Up next</CardTitle>
            {session.bench.length === 0 && (
              <p className="text-sm text-faint">Everyone is playing.</p>
            )}
            <ol className="space-y-1 text-sm">
              {session.bench.map((id, position) => (
                <li key={id} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-5 text-right font-data text-faint">
                      {position + 1}.
                    </span>
                    <Avatar name={playerName(id)} size="sm" />
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
                  <span className="font-data text-xs text-faint">
                    {session.gamesPlayed[id] ?? 0} played
                  </span>
                </li>
              ))}
            </ol>
            {session.bench.length > 0 && (
              <p className="mt-2 text-[11px] text-faint">
                Amber = fewest games (owed time). Queue is first-in-first-out.
              </p>
            )}
          </Card>

          <Card className="p-4">
            <CardTitle className="mb-2">Session record</CardTitle>
            <ul className="space-y-1 text-sm">
              {Object.entries(session.gamesPlayed)
                .sort(
                  (a, b) =>
                    (session.record[Number(b[0])]?.w ?? 0) -
                    (session.record[Number(a[0])]?.w ?? 0),
                )
                .map(([id, games]) => {
                  const rec = session.record[Number(id)] ?? {
                    w: 0,
                    l: 0,
                    d: 0,
                  }
                  return (
                    <li key={id} className="flex justify-between gap-2">
                      <span>{playerName(Number(id))}</span>
                      <span className="font-data text-mute">
                        {rec.w}–{rec.l}
                        {rec.d > 0 && `–${rec.d}`}{' '}
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
