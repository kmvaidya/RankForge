import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import GamePicker from '../components/GamePicker'
import {
  Card,
  EmptyState,
  ErrorNote,
  FairnessMeter,
  PageHeader,
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
  const [pairs, setPairs] = useState<{ kind: PairKind; a: number; b: number }[]>([])
  const [pairA, setPairA] = useState<number | ''>('')
  const [pairB, setPairB] = useState<number | ''>('')
  const [pairKind, setPairKind] = useState<PairKind>('together')
  const [result, setResult] = useState<MatchmakingResponse | null>(null)

  const { data: playersData, isPending } = useQuery({
    queryKey: ['players'],
    queryFn: listPlayers,
  })
  const players = playersData?.items ?? []
  const nameOf = (id: number) => players.find((p) => p.id === id)?.name ?? `#${id}`

  const generate = useMutation({
    mutationFn: generateTeams,
    onSuccess: setResult,
  })

  const togglePlayer = (id: number) => {
    setResult(null)
    setSelected((current) =>
      current.includes(id)
        ? current.filter((x) => x !== id)
        : [...current, id],
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
    navigate('/record', {
      state: { team1: teams[0] ?? [], team2: teams[1] ?? [] },
    })
  }

  return (
    <div>
      <PageHeader
        title="Matchmaking"
        subtitle="Generate the fairest possible teams from tonight's players"
        actions={<GamePicker />}
      />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">
              Who's playing? ({selected.length} selected)
            </h2>
            {isPending && <Spinner />}
            <div className="flex max-h-72 flex-col gap-1 overflow-y-auto pr-1">
              {players.map((player) => (
                <label
                  key={player.id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-800/60"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(player.id)}
                    onChange={() => togglePlayer(player.id)}
                    className="accent-indigo-500"
                  />
                  <span className="font-medium">{player.name}</span>
                </label>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">Options</h2>
            <label className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Teams</span>
              <select
                value={teamCount}
                onChange={(e) => setTeamCount(Number(e.target.value))}
                className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5"
              >
                {[2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>

            <div className="mt-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Constraints
              </h3>
              <div className="flex flex-wrap items-center gap-1.5 text-sm">
                <select
                  value={pairKind}
                  onChange={(e) => setPairKind(e.target.value as PairKind)}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                >
                  <option value="together">Keep together</option>
                  <option value="apart">Keep apart</option>
                </select>
                <select
                  value={pairA}
                  onChange={(e) => setPairA(e.target.value ? Number(e.target.value) : '')}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                >
                  <option value="">Player…</option>
                  {selected.map((id) => (
                    <option key={id} value={id}>
                      {nameOf(id)}
                    </option>
                  ))}
                </select>
                <select
                  value={pairB}
                  onChange={(e) => setPairB(e.target.value ? Number(e.target.value) : '')}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs"
                >
                  <option value="">Player…</option>
                  {selected.map((id) => (
                    <option key={id} value={id}>
                      {nameOf(id)}
                    </option>
                  ))}
                </select>
                <button
                  onClick={addPair}
                  disabled={pairA === '' || pairB === '' || pairA === pairB}
                  className="rounded-lg bg-slate-800 px-2.5 py-1 text-xs font-medium hover:bg-slate-700 disabled:opacity-40"
                >
                  Add
                </button>
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
                        ? 'bg-emerald-950/60 text-emerald-300'
                        : 'bg-red-950/60 text-red-300'
                    }`}
                  >
                    {pair.kind === 'together' ? '🤝' : '⚔️'} {nameOf(pair.a)} +{' '}
                    {nameOf(pair.b)} ✕
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleGenerate}
              disabled={
                gameId === null ||
                selected.length < Math.max(teamCount, 2) ||
                generate.isPending
              }
              className="mt-4 w-full rounded-lg bg-indigo-600 py-2.5 font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {generate.isPending ? 'Optimizing…' : 'Generate Teams'}
            </button>
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
              <p className="text-xs text-slate-500">
                {result.configurations_evaluated.toLocaleString()} configurations
                evaluated via {result.method}.
              </p>
              {result.configurations.map((config, index) => (
                <Card key={index} className="p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-slate-300">
                        Option {index + 1}
                      </span>
                      <FairnessMeter value={config.fairness} />
                    </div>
                    {/* Record Match supports two teams; hide the shortcut
                        for 3+ team configurations rather than silently
                        dropping teams. */}
                    {config.teams.length === 2 && (
                      <button
                        onClick={() =>
                          applyConfiguration(
                            config.teams.map((team) =>
                              team.map((member) => member.player.id),
                            ),
                          )
                        }
                        className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold hover:bg-slate-700"
                      >
                        Use this → Record
                      </button>
                    )}
                  </div>
                  <div
                    className="grid gap-3"
                    style={{
                      gridTemplateColumns: `repeat(${Math.min(
                        config.teams.length,
                        4,
                      )}, minmax(0, 1fr))`,
                    }}
                  >
                    {config.teams.map((team, teamIndex) => (
                      <div
                        key={teamIndex}
                        className="rounded-lg border border-slate-800 p-3"
                      >
                        <div className="mb-2 flex items-baseline justify-between">
                          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Team {teamIndex + 1}
                          </span>
                          <span className="text-xs tabular-nums text-slate-400">
                            μ {Math.round(config.team_ratings[teamIndex].mu)} ·{' '}
                            {(config.win_probabilities[teamIndex] * 100).toFixed(0)}
                            % win
                          </span>
                        </div>
                        <ul className="space-y-1">
                          {team.map((member) => (
                            <li
                              key={member.player.id}
                              className="flex items-center justify-between text-sm"
                            >
                              <span className="font-medium">
                                {member.player.name}
                              </span>
                              <span className="tabular-nums text-slate-500">
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
