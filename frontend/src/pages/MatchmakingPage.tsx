import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  Avatar,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorNote,
  FairnessMeter,
  Input,
  PageHeader,
  Pill,
  PlayerChip,
  SegmentedControl,
  Select,
  Spinner,
} from '../components/ui'
import { errorMessage, generateTeams, listPlayers } from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'
import type { MatchmakingResponse } from '../lib/types'

type PairKind = 'together' | 'apart'

export default function MatchmakingPage() {
  const { gameId } = useSelectedGame()
  const navigate = useNavigate()

  const [selected, setSelected] = useState<number[]>([])
  const [teamCount, setTeamCount] = useState(2)
  const [search, setSearch] = useState('')
  const [pairs, setPairs] = useState<{ kind: PairKind; a: number; b: number }[]>([])
  const [pairA, setPairA] = useState<number | ''>('')
  const [pairB, setPairB] = useState<number | ''>('')
  const [pairKind, setPairKind] = useState<PairKind>('together')
  const [result, setResult] = useState<MatchmakingResponse | null>(null)

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = useMemo(() => playersData?.items ?? [], [playersData])
  const nameOf = (id: number) => players.find((p) => p.id === id)?.name ?? `#${id}`

  const filteredPlayers = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q === ''
      ? players
      : players.filter((p) => p.name.toLowerCase().includes(q))
  }, [players, search])

  const generate = useMutation({
    mutationFn: generateTeams,
    onSuccess: setResult,
  })

  const togglePlayer = (id: number) => {
    setResult(null)
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    )
  }

  const addPair = () => {
    if (pairA === '' || pairB === '' || pairA === pairB) return
    setPairs((current) => [
      ...current,
      { kind: pairKind, a: Number(pairA), b: Number(pairB) },
    ])
    setPairA('')
    setPairB('')
  }

  const handleGenerate = () => {
    if (gameId === null || selected.length < teamCount) return
    generate.mutate({
      game_id: gameId,
      player_ids: selected,
      team_count: teamCount,
      num_results: 5,
      constraints: {
        together: pairs.filter((p) => p.kind === 'together').map((p) => [p.a, p.b]),
        apart: pairs.filter((p) => p.kind === 'apart').map((p) => [p.a, p.b]),
      },
    })
  }

  const applyConfiguration = (teams: number[][]) => {
    navigate('/record', { state: { teams } })
  }

  return (
    <div>
      <PageHeader
        title="Matchmaking"
        subtitle="Generate the fairest possible teams from tonight's players"
      />

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <div className="space-y-4">
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <CardTitle>Who's playing? ({selected.length})</CardTitle>
            </div>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search players…"
              className="mb-3 py-1.5"
            />
            {isPending && <Spinner />}
            <div className="flex max-h-80 flex-wrap content-start gap-1.5 overflow-y-auto pr-1">
              {filteredPlayers.map((player) => (
                <PlayerChip
                  key={player.id}
                  name={player.name}
                  active={selected.includes(player.id)}
                  onClick={() => togglePlayer(player.id)}
                />
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <CardTitle className="mb-3">Options</CardTitle>
            <div className="flex items-center justify-between gap-2">
              <span className="font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Teams
              </span>
              <SegmentedControl
                size="sm"
                options={[2, 3, 4].map((n) => ({ value: n, label: n }))}
                value={teamCount}
                onChange={(n) => {
                  setResult(null)
                  setTeamCount(n)
                }}
              />
            </div>

            <div className="mt-4">
              <h3 className="mb-2 font-display text-xs font-semibold uppercase tracking-wider text-faint">
                Constraints
              </h3>
              <div className="flex flex-wrap items-center gap-1.5 text-sm">
                <Select
                  value={pairKind}
                  onChange={(e) => setPairKind(e.target.value as PairKind)}
                  className="w-auto px-2 py-1 text-xs"
                >
                  <option value="together">Keep together</option>
                  <option value="apart">Keep apart</option>
                </Select>
                <Select
                  value={pairA}
                  onChange={(e) => setPairA(e.target.value ? Number(e.target.value) : '')}
                  className="w-auto px-2 py-1 text-xs"
                >
                  <option value="">Player…</option>
                  {selected.map((id) => (
                    <option key={id} value={id}>
                      {nameOf(id)}
                    </option>
                  ))}
                </Select>
                <Select
                  value={pairB}
                  onChange={(e) => setPairB(e.target.value ? Number(e.target.value) : '')}
                  className="w-auto px-2 py-1 text-xs"
                >
                  <option value="">Player…</option>
                  {selected.map((id) => (
                    <option key={id} value={id}>
                      {nameOf(id)}
                    </option>
                  ))}
                </Select>
                <Button
                  size="sm"
                  onClick={addPair}
                  disabled={pairA === '' || pairB === '' || pairA === pairB}
                >
                  Add
                </Button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {pairs.map((pair, index) => (
                  <button
                    key={index}
                    onClick={() =>
                      setPairs((current) => current.filter((_, i) => i !== index))
                    }
                    title="Remove constraint"
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      pair.kind === 'together'
                        ? 'bg-win/10 text-win'
                        : 'bg-loss/10 text-loss'
                    }`}
                  >
                    {pair.kind === 'together' ? '🤝' : '⚔️'} {nameOf(pair.a)} +{' '}
                    {nameOf(pair.b)} ✕
                  </button>
                ))}
              </div>
            </div>

            <Button
              variant="primary"
              onClick={handleGenerate}
              disabled={
                gameId === null ||
                selected.length < Math.max(teamCount, 2) ||
                generate.isPending
              }
              className="mt-4 w-full"
            >
              {generate.isPending ? 'Optimizing…' : 'Generate teams'}
            </Button>
          </Card>
        </div>

        <div className="space-y-4">
          {generate.error && <ErrorNote message={errorMessage(generate.error)} />}

          {!result && !generate.isPending && (
            <EmptyState
              title="No teams generated yet"
              hint="Pick at least two players and hit Generate."
            />
          )}
          {generate.isPending && <Spinner label="Searching configurations…" />}

          {result && (
            <>
              <p className="text-xs text-faint">
                <span className="font-data">
                  {result.configurations_evaluated.toLocaleString()}
                </span>{' '}
                configurations evaluated via {result.method}.
              </p>
              {result.configurations.map((config, index) => (
                <Card key={index} className="p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <span className="font-display text-sm font-bold uppercase tracking-wider text-mute">
                        Option {index + 1}
                      </span>
                      <FairnessMeter value={config.fairness} />
                      {config.lopsided && <Pill tone="warn">lopsided</Pill>}
                    </div>
                    <Button
                      size="sm"
                      onClick={() =>
                        applyConfiguration(
                          config.teams.map((team) =>
                            team.map((member) => member.player.id),
                          ),
                        )
                      }
                    >
                      Use this → Record
                    </Button>
                  </div>
                  <div
                    className="grid gap-3"
                    style={{
                      gridTemplateColumns:
                        'repeat(auto-fit, minmax(180px, 1fr))',
                    }}
                  >
                    {config.teams.map((team, teamIndex) => (
                      <div
                        key={teamIndex}
                        className="rounded-lg border border-line p-3"
                      >
                        <div className="mb-2 flex items-baseline justify-between">
                          <span className="font-display text-xs font-semibold uppercase tracking-wider text-faint">
                            Team {teamIndex + 1}
                          </span>
                          <span className="font-data text-xs text-mute">
                            μ {Math.round(config.team_ratings[teamIndex].mu)} ·{' '}
                            {(config.win_probabilities[teamIndex] * 100).toFixed(0)}
                            %
                          </span>
                        </div>
                        <ul className="space-y-1">
                          {team.map((member) => (
                            <li
                              key={member.player.id}
                              className="flex items-center justify-between gap-2 text-sm"
                            >
                              <span className="flex min-w-0 items-center gap-1.5 font-medium">
                                <Avatar name={member.player.name} size="sm" />
                                <span className="truncate">
                                  {member.player.name}
                                </span>
                              </span>
                              <span className="font-data text-faint">
                                {Math.round(member.rating)}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
