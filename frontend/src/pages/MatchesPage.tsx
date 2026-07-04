import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  RatingDelta,
  Spinner,
  SuccessNote,
} from '../components/ui'
import { deleteMatch, errorMessage, listMatches } from '../lib/api'
import { useSelectedGame } from '../lib/GameContext'
import { outcomeLabel } from '../lib/outcome'
import type { Match } from '../lib/types'

const PAGE_SIZE = 20

function teamsOf(match: Match): Map<number, Match['participants']> {
  const teams = new Map<number, Match['participants']>()
  for (const participant of match.participants) {
    const list = teams.get(participant.team_id) ?? []
    list.push(participant)
    teams.set(participant.team_id, list)
  }
  return teams
}

export default function MatchesPage() {
  const { gameId } = useSelectedGame()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Reset pagination when switching games, otherwise a deep page offset can
  // outrun the new game's match count and show a false empty state.
  const [lastGameId, setLastGameId] = useState(gameId)
  if (gameId !== lastGameId) {
    setLastGameId(gameId)
    setPage(0)
  }

  const { data, isPending, error } = useQuery({
    queryKey: ['matches', gameId, page],
    queryFn: () =>
      listMatches({
        game_id: gameId ?? undefined,
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
    enabled: gameId !== null,
  })

  const remove = useMutation({
    mutationFn: deleteMatch,
    onSuccess: () => {
      setConfirmDeleteId(null)
      setNotice(
        'Match deleted. Ratings for all subsequent matches were recalculated.',
      )
      queryClient.invalidateQueries({ queryKey: ['matches'] })
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
    },
  })

  return (
    <div>
      <PageHeader
        title="Matches"
        subtitle="Full match history — deleting a match replays every rating after it"
      />

      {notice && (
        <div className="mb-4">
          <SuccessNote>{notice}</SuccessNote>
        </div>
      )}
      {error && <ErrorNote message={errorMessage(error)} />}
      {remove.error && <ErrorNote message={errorMessage(remove.error)} />}
      {isPending && gameId !== null && <Spinner />}

      {data && data.items.length === 0 && (
        <EmptyState title="No matches recorded" hint="Record one to see it here." />
      )}

      <div className="space-y-3">
        {data?.items.map((match) => {
          const teams = [...teamsOf(match).entries()].sort(
            ([a], [b]) => a - b,
          )
          const metadata = match.match_metadata ?? {}
          return (
            <Card key={match.id} className="p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                <div className="text-mute">
                  <span className="font-semibold text-mute">
                    #{match.id}
                  </span>{' '}
                  · {new Date(match.played_at).toLocaleString()}
                  {typeof metadata.final_score === 'string' && (
                    <span className="ml-2 rounded bg-raised px-1.5 py-0.5 text-xs">
                      {metadata.final_score}
                    </span>
                  )}
                </div>
                {confirmDeleteId === match.id ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-loss">
                      Delete and recalculate?
                    </span>
                    <button
                      onClick={() => remove.mutate(match.id)}
                      disabled={remove.isPending}
                      className="rounded border border-loss/40 bg-loss/10 px-2.5 py-1 text-xs font-semibold text-loss hover:bg-loss/20"
                    >
                      {remove.isPending ? 'Deleting…' : 'Confirm'}
                    </button>
                    <button
                      onClick={() => setConfirmDeleteId(null)}
                      className="rounded bg-raised px-2.5 py-1 text-xs hover:bg-line"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDeleteId(match.id)}
                    className="rounded bg-raised px-2.5 py-1 text-xs text-mute hover:bg-loss/10 hover:text-loss"
                  >
                    Delete
                  </button>
                )}
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                {teams.map(([teamId, members]) => (
                  <div
                    key={teamId}
                    className="rounded bg-raised px-3 py-2"
                  >
                    <p className="mb-1 font-display text-xs font-semibold uppercase tracking-wider text-faint">
                      Team {teamId}
                    </p>
                    <ul className="space-y-0.5 text-sm">
                      {members.map((participant) => {
                        const label = outcomeLabel(participant.outcome)
                        return (
                          <li
                            key={participant.id}
                            className="flex items-center justify-between"
                          >
                            <span>
                              <Link
                                to={`/players/${participant.player.id}`}
                                className="font-medium hover:underline"
                              >
                                {participant.player.name}
                              </Link>
                              <span
                                className={`ml-2 text-xs font-semibold uppercase ${
                                  label === 'win'
                                    ? 'text-win'
                                    : label === 'loss'
                                      ? 'text-loss'
                                      : 'text-faint'
                                }`}
                              >
                                {label}
                              </span>
                            </span>
                            {participant.rating_info_change && (
                              <RatingDelta
                                value={
                                  participant.rating_info_change.rating_change
                                }
                              />
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </Card>
          )
        })}
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-6 flex items-center justify-between text-sm">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded bg-raised px-3 py-1.5 font-medium hover:bg-line disabled:opacity-40"
          >
            ← Newer
          </button>
          <span className="text-faint">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)}{' '}
            of {data.total}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!data.has_more}
            className="rounded bg-raised px-3 py-1.5 font-medium hover:bg-line disabled:opacity-40"
          >
            Older →
          </button>
        </div>
      )}
    </div>
  )
}
