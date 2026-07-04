import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import BulkAddPlayers from '../components/BulkAddPlayers'
import {
  Button,
  Card,
  CardTitle,
  ErrorNote,
  Field,
  Input,
  PageHeader,
  Pill,
  PlayerChip,
  ProbBar,
  RatingDelta,
  SegmentedControl,
  Spinner,
  SuccessNote,
  Textarea,
} from '../components/ui'
import {
  createMatch,
  createPlayer,
  errorMessage,
  listGames,
  listPlayers,
  predictMatch,
} from '../lib/api'
import { useFeature } from '../lib/features'
import { useSelectedGame } from '../lib/GameContext'
import type { Match, ParticipantCreate } from '../lib/types'

const MAX_TEAMS = 8

interface TeamState {
  key: number
  members: number[]
  score: string
  /** Ranked mode: shares the finishing rank of the team above. */
  tiedWithPrev: boolean
}

/** Teams passed from the Matchmaking page via router state. */
interface PrefillState {
  teams?: number[][]
  /** Legacy two-team shape (older links). */
  team1?: number[]
  team2?: number[]
}

let nextKey = 1
function makeTeam(members: number[] = []): TeamState {
  return { key: nextKey++, members, score: '', tiedWithPrev: false }
}

function prefillTeams(state: PrefillState): TeamState[] {
  const teams =
    state.teams ??
    (state.team1 || state.team2 ? [state.team1 ?? [], state.team2 ?? []] : null)
  if (!teams || teams.length < 2) return [makeTeam(), makeTeam()]
  return teams.map((members) => makeTeam(members))
}

/** Competition ranking over the ordered team list: ties share a rank and
 *  the next untied team skips past the whole tie group (1, 1, 3…). */
function deriveRanks(teams: TeamState[]): number[] {
  const ranks: number[] = []
  teams.forEach((team, index) => {
    if (index === 0) ranks.push(1)
    else ranks.push(team.tiedWithPrev ? ranks[index - 1] : index + 1)
  })
  return ranks
}

function parseScore(raw: string): number | null {
  if (raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 0 ? n : null
}

type Winner = 'A' | 'draw' | 'B'

export default function RecordMatchPage() {
  const { gameId } = useSelectedGame()
  const queryClient = useQueryClient()
  const prefill = (useLocation().state ?? {}) as PrefillState

  const [teams, setTeams] = useState<TeamState[]>(() => prefillTeams(prefill))
  const [armedKey, setArmedKey] = useState<number | null>(null)
  const [ffa, setFfa] = useState(false)
  const [winner, setWinner] = useState<Winner>('A')
  const [search, setSearch] = useState('')
  const [notes, setNotes] = useState('')
  const [weight, setWeight] = useState('')
  const [playedAt, setPlayedAt] = useState('')
  const [newPlayerName, setNewPlayerName] = useState('')
  const [result, setResult] = useState<Match | null>(null)
  /** Set at submit time when the recorded winner defied the odds. */
  const [upset, setUpset] = useState<{ label: string; odds: number } | null>(
    null,
  )

  const weightsEnabled = useFeature('match_weights')
  const weightValue = weight.trim() === '' ? 1 : Number(weight)
  const weightValid = Number.isFinite(weightValue) && weightValue > 0

  // Binary (win/draw/loss) for classic two-team matches; every other shape
  // — 3+ teams or free-for-all — records a finishing order.
  const ranked = ffa || teams.length > 2

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = useMemo(() => playersData?.items ?? [], [playersData])
  const playerName = (id: number) =>
    players.find((p) => p.id === id)?.name ?? `#${id}`

  // The selected game's quick-entry preset (rating_config.score_preset):
  // tapping the winner auto-fills scores for two-tap recording.
  const { data: gamesData } = useQuery({ queryKey: ['games'], queryFn: listGames })
  const scorePreset = gamesData?.items.find((g) => g.id === gameId)
    ?.rating_config?.score_preset
  const preset = typeof scorePreset === 'number' ? scorePreset : null

  const assignedTeam = (playerId: number): TeamState | undefined =>
    teams.find((team) => team.members.includes(playerId))
  const armed = teams.find((team) => team.key === armedKey) ?? teams[0]

  const clearResult = () => {
    setResult(null)
    setUpset(null)
  }

  const togglePlayer = (playerId: number) => {
    clearResult()
    if (ffa) {
      // Free-for-all: every tap adds/removes a solo team.
      setTeams((current) => {
        const existing = current.find((t) => t.members.includes(playerId))
        if (existing) return current.filter((t) => t.key !== existing.key)
        return [...current, makeTeam([playerId])]
      })
      return
    }
    const target = armed
    if (!target) return
    setTeams((current) =>
      current.map((team) => {
        const has = team.members.includes(playerId)
        if (team.key === target.key)
          return has
            ? { ...team, members: team.members.filter((id) => id !== playerId) }
            : { ...team, members: [...team.members, playerId] }
        return has
          ? { ...team, members: team.members.filter((id) => id !== playerId) }
          : team
      }),
    )
  }

  const removeFromTeam = (teamKey: number, playerId: number) => {
    clearResult()
    setTeams((current) =>
      ffa
        ? current.filter((t) => t.key !== teamKey)
        : current.map((team) =>
            team.key === teamKey
              ? {
                  ...team,
                  members: team.members.filter((id) => id !== playerId),
                }
              : team,
          ),
    )
  }

  const addTeam = () => {
    clearResult()
    setTeams((current) => {
      if (current.length >= MAX_TEAMS) return current
      const team = makeTeam()
      setArmedKey(team.key)
      return [...current, team]
    })
  }

  const removeTeam = (teamKey: number) => {
    clearResult()
    setTeams((current) =>
      current.length > 2 ? current.filter((t) => t.key !== teamKey) : current,
    )
  }

  const toggleFfa = () => {
    clearResult()
    if (!ffa) {
      // Every assigned player becomes their own team.
      const assigned = teams.flatMap((team) => team.members)
      setTeams(
        assigned.length >= 2
          ? assigned.map((id) => makeTeam([id]))
          : [makeTeam(), makeTeam()],
      )
    } else {
      setTeams([makeTeam(), makeTeam()])
    }
    setArmedKey(null)
    setFfa(!ffa)
  }

  const moveTeam = (index: number, delta: -1 | 1) => {
    clearResult()
    setTeams((current) => {
      const target = index + delta
      if (target < 0 || target >= current.length) return current
      const next = [...current]
      const [team] = next.splice(index, 1)
      next.splice(target, 0, team)
      return next.map((t, i) => (i === 0 ? { ...t, tiedWithPrev: false } : t))
    })
  }

  const toggleTie = (teamKey: number) => {
    clearResult()
    setTeams((current) =>
      current.map((team, index) =>
        team.key === teamKey && index > 0
          ? { ...team, tiedWithPrev: !team.tiedWithPrev }
          : team,
      ),
    )
  }

  const setScore = (teamKey: number, value: string) => {
    setTeams((current) =>
      current.map((team) =>
        team.key === teamKey ? { ...team, score: value } : team,
      ),
    )
  }

  const teamLabel = (team: TeamState, index: number) =>
    team.members.length === 1
      ? playerName(team.members[0])
      : `Team ${index + 1}`

  // --- Validation ------------------------------------------------------------

  const allNonEmpty =
    teams.length >= 2 && teams.every((t) => t.members.length > 0)
  const scoresEntered = teams.filter((t) => t.score.trim() !== '').length
  const scoresValid =
    scoresEntered === 0 ||
    (scoresEntered === teams.length &&
      teams.every((t) => parseScore(t.score) !== null))
  const playedAtValid =
    playedAt === '' || !Number.isNaN(new Date(playedAt).getTime())

  // --- Prediction ------------------------------------------------------------

  const memberLists = teams.map((t) => t.members)
  const predictKey = memberLists
    .map((m) => [...m].sort((a, b) => a - b).join(','))
    .join('|')
  const prediction = useQuery({
    queryKey: ['predict', gameId, predictKey],
    queryFn: () => predictMatch(gameId!, memberLists),
    enabled: gameId !== null && allNonEmpty,
    staleTime: 30_000,
  })
  const odds = prediction.data

  // --- Mutations ------------------------------------------------------------

  const addPlayer = useMutation({
    mutationFn: createPlayer,
    onSuccess: () => {
      setNewPlayerName('')
      queryClient.invalidateQueries({ queryKey: ['players'] })
    },
  })

  const submit = useMutation({
    mutationFn: createMatch,
    onSuccess: (match) => {
      setResult(match)
      setTeams([makeTeam(), makeTeam()])
      setFfa(false)
      setArmedKey(null)
      setWinner('A')
      setNotes('')
      setWeight('')
      setPlayedAt('')
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
      queryClient.invalidateQueries({ queryKey: ['matches'] })
    },
  })

  const canSubmit =
    gameId !== null &&
    allNonEmpty &&
    weightValid &&
    scoresValid &&
    playedAtValid &&
    !submit.isPending

  /** Two-tap entry: picking the winner drafts the score line when the game
   *  has a preset and nothing has been typed yet (two-team mode only). */
  const pickWinner = (value: Winner) => {
    setWinner(value)
    if (preset === null || value === 'draw' || ranked) return
    if (teams.every((t) => t.score.trim() === '')) {
      setTeams((current) =>
        current.map((team, index) => ({
          ...team,
          score: String(
            (value === 'A' && index === 0) || (value === 'B' && index === 1)
              ? preset
              : 0,
          ),
        })),
      )
    }
  }

  const handleSubmit = () => {
    if (!canSubmit) return
    const ranks = deriveRanks(teams)

    // Judge the upset from the odds as they stood at submit time. The bar
    // for "upset" scales with field size: winning at under 70% of an even
    // share of the field counts.
    const winnerIndex = ranked
      ? ranks.indexOf(1)
      : winner === 'A'
        ? 0
        : winner === 'B'
          ? 1
          : -1
    if (winnerIndex >= 0 && odds) {
      const winnerOdds = odds.teams[winnerIndex]?.win_probability
      const threshold = (1 / teams.length) * 0.7
      setUpset(
        winnerOdds !== undefined && winnerOdds < threshold
          ? {
              label: teamLabel(teams[winnerIndex], winnerIndex),
              odds: winnerOdds,
            }
          : null,
      )
    } else {
      setUpset(null)
    }

    const outcomeFor = (index: number): ParticipantCreate['outcome'] => {
      if (ranked) return { rank: ranks[index] }
      if (winner === 'draw') return { result: 'draw' }
      const won = (winner === 'A') === (index === 0)
      return { result: won ? 'win' : 'loss' }
    }

    const participants: ParticipantCreate[] = teams.flatMap((team, index) =>
      team.members.map((playerId) => ({
        player_id: playerId,
        team_id: index + 1,
        outcome: outcomeFor(index),
      })),
    )

    const metadata: Record<string, unknown> = {}
    if (scoresEntered === teams.length) {
      const scores: Record<string, number> = {}
      teams.forEach((team, index) => {
        scores[String(index + 1)] = parseScore(team.score)!
      })
      metadata.team_scores = scores
      if (teams.length === 2)
        metadata.final_score = `${scores['1']}-${scores['2']}`
    }
    if (notes.trim()) metadata.notes = notes.trim()
    if (weightsEnabled && weight.trim() && weightValue !== 1)
      metadata.weight = weightValue

    submit.mutate({
      game_id: gameId!,
      participants,
      match_metadata: metadata,
      ...(playedAt !== ''
        ? { played_at: new Date(playedAt).toISOString() }
        : {}),
    })
  }

  // --- Derived display -------------------------------------------------------

  const ranks = deriveRanks(teams)
  const filteredPlayers = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q === ''
      ? players
      : players.filter((p) => p.name.toLowerCase().includes(q))
  }, [players, search])

  const resultTeams = useMemo(() => {
    if (!result) return []
    const byTeam = new Map<number, Match['participants']>()
    for (const p of result.participants) {
      byTeam.set(p.team_id, [...(byTeam.get(p.team_id) ?? []), p])
    }
    return [...byTeam.entries()].sort(([a], [b]) => a - b)
  }, [result])

  return (
    <div>
      <PageHeader
        title="Record match"
        subtitle="Ratings update the moment you submit"
        actions={
          <SegmentedControl
            options={[
              { value: 'teams', label: 'Teams' },
              { value: 'ffa', label: 'Free-for-all' },
            ]}
            value={ffa ? 'ffa' : 'teams'}
            onChange={(mode) => {
              if ((mode === 'ffa') !== ffa) toggleFfa()
            }}
          />
        }
      />

      {result && (
        <div className="mb-6 space-y-3">
          <SuccessNote>
            Match #{result.id} recorded — rating changes below.
            {upset && (
              <span className="ml-2 font-semibold text-warn">
                Upset: {upset.label} won at {Math.round(upset.odds * 100)}%
                odds.
              </span>
            )}
          </SuccessNote>
          <Card className="p-4">
            <div className="grid gap-2 sm:grid-cols-2">
              {resultTeams.map(([teamId, members]) => (
                <div key={teamId} className="rounded bg-raised px-3 py-2">
                  <p className="mb-1 font-display text-xs font-semibold uppercase tracking-wider text-faint">
                    Team {teamId}
                  </p>
                  {members.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center justify-between py-0.5"
                    >
                      <Link
                        to={`/players/${p.player.id}`}
                        className="text-sm font-medium hover:text-ember"
                      >
                        {p.player.name}
                      </Link>
                      <span className="font-data text-sm">
                        {p.rating_info_before
                          ? Math.round(p.rating_info_before.rating)
                          : '—'}{' '}
                        →{' '}
                        {p.rating_info_before && p.rating_info_change ? (
                          <>
                            <strong>
                              {Math.round(
                                p.rating_info_before.rating +
                                  p.rating_info_change.rating_change,
                              )}
                            </strong>{' '}
                            <RatingDelta
                              value={p.rating_info_change.rating_change}
                            />
                          </>
                        ) : (
                          '—'
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          {/* --- Teams --------------------------------------------------- */}
          {!ffa && (
            <div className="grid gap-3 sm:grid-cols-2">
              {teams.map((team, index) => {
                const isArmed = armed?.key === team.key
                return (
                  <div
                    key={team.key}
                    role="button"
                    tabIndex={0}
                    onClick={() => setArmedKey(team.key)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') setArmedKey(team.key)
                    }}
                    className={`cursor-pointer rounded-lg border p-3 text-left transition-colors ${
                      isArmed
                        ? 'border-ember/70 bg-ember/5'
                        : 'border-line hover:border-line-strong'
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="font-display text-sm font-semibold uppercase tracking-wider text-mute">
                        Team {index + 1}
                        {ranked && (
                          <span className="ml-2 font-data text-xs normal-case text-faint">
                            finishes #{ranks[index]}
                          </span>
                        )}
                      </span>
                      <span className="flex items-center gap-1">
                        {isArmed && (
                          <span className="text-[11px] font-medium text-ember">
                            tap players to fill
                          </span>
                        )}
                        {teams.length > 2 && (
                          <button
                            aria-label={`Remove team ${index + 1}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              removeTeam(team.key)
                            }}
                            className="px-1 text-faint hover:text-loss"
                          >
                            ✕
                          </button>
                        )}
                      </span>
                    </div>
                    <div className="flex min-h-8 flex-wrap gap-1.5">
                      {team.members.map((id) => (
                        <PlayerChip
                          key={id}
                          name={playerName(id)}
                          onRemove={() => removeFromTeam(team.key, id)}
                        />
                      ))}
                      {team.members.length === 0 && (
                        <span className="text-xs text-faint">
                          {isArmed
                            ? 'Tap players below…'
                            : 'Tap here, then pick players'}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
              {teams.length < MAX_TEAMS && (
                <button
                  onClick={addTeam}
                  className="rounded-lg border border-dashed border-line py-4 text-sm font-medium text-faint transition-colors hover:border-ember/60 hover:text-ember"
                >
                  + Add team
                </button>
              )}
            </div>
          )}

          {/* --- Finishing order (ranked mode) ----------------------------- */}
          {ranked && teams.length >= 2 && (
            <Card className="p-4">
              <CardTitle className="mb-1">Finishing order</CardTitle>
              <p className="mb-3 text-xs text-faint">
                Top row finished first. Use the arrows to reorder
                {ffa ? ' players' : ' teams'}; “=” ties a row with the one
                above it.
              </p>
              <ol className="space-y-1">
                {teams.map((team, index) => (
                  <li
                    key={team.key}
                    className="flex items-center gap-2 rounded bg-raised px-2 py-1.5"
                  >
                    <span className="w-7 text-center font-data text-sm font-semibold text-mute">
                      {ranks[index]}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                      {team.members.map((id) => (
                        <PlayerChip
                          key={id}
                          name={playerName(id)}
                          onRemove={() => removeFromTeam(team.key, id)}
                        />
                      ))}
                      {!ffa && team.members.length !== 1 && (
                        <span className="text-xs text-faint">
                          Team {index + 1}
                        </span>
                      )}
                    </span>
                    {index > 0 && (
                      <button
                        onClick={() => toggleTie(team.key)}
                        title="Tied with the row above"
                        aria-pressed={team.tiedWithPrev}
                        className={`rounded px-2 py-1 font-data text-xs font-semibold transition-colors ${
                          team.tiedWithPrev
                            ? 'bg-warn/15 text-warn'
                            : 'bg-surface text-faint hover:text-ink'
                        }`}
                      >
                        =
                      </button>
                    )}
                    <span className="flex flex-col">
                      <button
                        onClick={() => moveTeam(index, -1)}
                        disabled={index === 0}
                        aria-label="Move up"
                        className="px-1.5 text-xs text-faint hover:text-ink disabled:opacity-30"
                      >
                        ▲
                      </button>
                      <button
                        onClick={() => moveTeam(index, 1)}
                        disabled={index === teams.length - 1}
                        aria-label="Move down"
                        className="px-1.5 text-xs text-faint hover:text-ink disabled:opacity-30"
                      >
                        ▼
                      </button>
                    </span>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {/* --- Odds ------------------------------------------------------- */}
          {allNonEmpty && odds && odds.teams.length === teams.length && (
            <Card className="p-3">
              <div className="mb-1.5 flex items-center justify-between text-xs text-faint">
                <span>Pre-match odds</span>
                {odds.lopsided && <Pill tone="warn">lopsided matchup</Pill>}
              </div>
              <ProbBar
                segments={odds.teams.map((team, index) => ({
                  label: teamLabel(teams[index], index),
                  probability: team.win_probability,
                }))}
              />
            </Card>
          )}

          {/* --- Player pool ------------------------------------------------ */}
          <Card className="p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <CardTitle>
                {ffa ? 'Tap everyone who played' : 'Assign players'}
              </CardTitle>
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search players…"
                className="max-w-44 py-1.5"
              />
            </div>
            {isPending && <Spinner />}
            <div className="flex flex-wrap gap-1.5">
              {filteredPlayers.map((player) => {
                const team = assignedTeam(player.id)
                const teamIndex = team
                  ? teams.findIndex((t) => t.key === team.key)
                  : -1
                const inArmed = !ffa && team && armed && team.key === armed.key
                return (
                  <span key={player.id} className="relative">
                    <PlayerChip
                      name={player.name}
                      active={Boolean(team)}
                      onClick={() => togglePlayer(player.id)}
                    />
                    {team && !ffa && !inArmed && (
                      <span className="absolute -right-1 -top-1 rounded-sm bg-line px-1 font-data text-[9px] font-semibold text-mute">
                        T{teamIndex + 1}
                      </span>
                    )}
                  </span>
                )
              })}
              {filteredPlayers.length === 0 && !isPending && (
                <span className="text-sm text-faint">No players match.</span>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <Input
                value={newPlayerName}
                onChange={(e) => setNewPlayerName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newPlayerName.trim().length >= 2)
                    addPlayer.mutate(newPlayerName.trim())
                }}
                placeholder="New player name…"
                className="flex-1"
              />
              <Button
                onClick={() => addPlayer.mutate(newPlayerName.trim())}
                disabled={newPlayerName.trim().length < 2 || addPlayer.isPending}
              >
                Add player
              </Button>
            </div>
            {addPlayer.error && (
              <p className="mt-2 text-sm text-loss">
                {errorMessage(addPlayer.error)}
              </p>
            )}
            <BulkAddPlayers />
          </Card>
        </div>

        {/* --- Result column ---------------------------------------------- */}
        <div className="space-y-4">
          <Card className="p-4">
            <CardTitle className="mb-3">Result</CardTitle>

            {!ranked && (
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ['A', teams[0] ? `${teamLabel(teams[0], 0)} won` : 'Team 1 won'],
                    ['draw', 'Draw'],
                    ['B', teams[1] ? `${teamLabel(teams[1], 1)} won` : 'Team 2 won'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => pickWinner(value)}
                    title={label}
                    className={`truncate rounded px-2 py-2 text-xs font-semibold transition-colors ${
                      winner === value
                        ? 'bg-ember text-ember-ink'
                        : 'bg-raised text-mute hover:bg-line hover:text-ink'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            {ranked && (
              <p className="text-xs text-faint">
                Outcome comes from the finishing order on the left — rank 1
                wins, ties allowed.
              </p>
            )}

            <div className="mt-4 space-y-2">
              <p className="font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Scores (optional)
              </p>
              <div className="grid grid-cols-2 gap-2">
                {teams.map((team, index) => (
                  <Input
                    key={team.key}
                    value={team.score}
                    onChange={(e) => setScore(team.key, e.target.value)}
                    inputMode="numeric"
                    invalid={!scoresValid && team.score.trim() === ''}
                    placeholder={teamLabel(team, index)}
                    title={`${teamLabel(team, index)} score`}
                    className="py-1.5"
                  />
                ))}
              </div>
              {!scoresValid && (
                <p className="text-xs text-loss">
                  Enter a score for every team, or leave them all empty.
                </p>
              )}
            </div>

            {weightsEnabled && (
              <Field
                label="Match weight (optional)"
                hint="Scales how much this match moves ratings."
                className="mt-3"
              >
                <Input
                  value={weight}
                  onChange={(e) => setWeight(e.target.value)}
                  inputMode="decimal"
                  invalid={!weightValid}
                  placeholder="1 = normal, 5 = counts 5×"
                />
              </Field>
            )}

            <Field
              label="Played earlier (optional)"
              hint="Backdating replays every later match's ratings."
              className="mt-3"
            >
              <Input
                type="datetime-local"
                value={playedAt}
                onChange={(e) => setPlayedAt(e.target.value)}
                invalid={!playedAtValid}
              />
            </Field>

            <Field label="Notes (optional)" className="mt-3">
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
              />
            </Field>

            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="mt-4 w-full py-2.5"
            >
              {submit.isPending ? 'Submitting…' : 'Submit match'}
            </Button>
            {!allNonEmpty && (
              <p className="mt-2 text-xs text-faint">
                {ffa
                  ? 'Tap at least two players.'
                  : 'Every team needs at least one player.'}
              </p>
            )}
            {submit.error && (
              <div className="mt-3">
                <ErrorNote message={errorMessage(submit.error)} />
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
