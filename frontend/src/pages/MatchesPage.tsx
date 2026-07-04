import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Button,
  Card,
  ConfirmButton,
  EmptyState,
  ErrorNote,
  PageHeader,
  Pill,
  RatingDelta,
  Spinner,
  SuccessNote,
} from '../components/ui'
import { deleteMatch, errorMessage, listMatches } from '../lib/api'
import { absoluteTime, relativeTime } from '../lib/format'
import { useSelectedGame } from '../lib/GameContext'
import { outcomeClass, outcomeLabel } from '../lib/outcome'
import type { Match, Outcome } from '../lib/types'

const PAGE_SIZE = 20

function teamsOf(match: Match): [number, Match['participants']][] {
  const teams = new Map<number, Match['participants']>()
  for (const participant of match.participants) {
    const list = teams.get(participant.team_id) ?? []
    list.push(participant)
    teams.set(participant.team_id, list)
  }
  return [...teams.entries()].sort(([a], [b]) => a - b)
}

function outcomePill(outcome: Outcome) {
  const klass = outcomeClass(outcome)
  const label = outcomeLabel(outcome)
  const tone =
    klass === 'win' ? 'win' : klass === 'loss' ? 'loss' : ('draw' as const)
  // Ranked outcomes read as their placement, colored by win/loss.
  const text =
    'rank' in outcome && typeof outcome.rank === 'number'
      ? `#${outcome.rank}`
      : label
  return <Pill tone={tone}>{text}</Pill>
}

export default function MatchesPage() {
  const { gameId } = useSelectedGame()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)
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
          const teams = teamsOf(match)
          const metadata = match.match_metadata ?? {}
          const teamScores = (metadata.team_scores ?? null) as Record<
            string,
            number
          > | null
          const weight =
            typeof metadata.weight === 'number' && metadata.weight !== 1
              ? metadata.weight
              : null
          return (
            <Card key={match.id} className="p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                <div className="flex flex-wrap items-center gap-2 text-mute">
                  <span className="font-data text-faint">#{match.id}</span>
                  <span title={absoluteTime(match.played_at)}>
                    {relativeTime(match.played_at)}
                  </span>
                  {typeof metadata.final_score === 'string' && (
                    <span className="rounded bg-raised px-1.5 py-0.5 font-data text-xs">
                      {metadata.final_score}
                    </span>
                  )}
                  {typeof metadata.session_name === 'string' && (
                    <Pill tone="flag">{metadata.session_name}</Pill>
                  )}
                  {weight !== null && <Pill tone="warn">weight ×{weight}</Pill>}
                </div>
                <ConfirmButton
                  prompt="Delete and recalculate?"
                  confirmLabel="Delete"
                  busyLabel="Deleting…"
                  busy={remove.isPending}
                  onConfirm={() => remove.mutate(match.id)}
                >
                  Delete
                </ConfirmButton>
              </div>

              <div
                className="grid gap-2"
                style={{
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                }}
              >
                {teams.map(([teamId, members]) => (
                  <div key={teamId} className="rounded bg-raised px-3 py-2">
                    <p className="mb-1 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 font-display text-xs font-semibold uppercase tracking-wider text-faint">
                        {members.length === 1
                          ? members[0].player.name
                          : `Team ${teamId}`}
                        {members[0] && outcomePill(members[0].outcome)}
                      </span>
                      {teamScores &&
                        typeof teamScores[String(teamId)] === 'number' && (
                          <span className="font-data text-sm font-semibold text-ink">
                            {teamScores[String(teamId)]}
                          </span>
                        )}
                    </p>
                    <ul className="space-y-0.5 text-sm">
                      {members.map((participant) => (
                        <li
                          key={participant.id}
                          className="flex items-center justify-between"
                        >
                          <Link
                            to={`/players/${participant.player.id}`}
                            className="font-medium hover:text-ember"
                          >
                            {participant.player.name}
                          </Link>
                          {participant.rating_info_change && (
                            <RatingDelta
                              value={participant.rating_info_change.rating_change}
                            />
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
              {typeof metadata.notes === 'string' && metadata.notes !== '' && (
                <p className="mt-2 text-xs italic text-faint">
                  {metadata.notes}
                </p>
              )}
            </Card>
          )
        })}
      </div>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-6 flex items-center justify-between text-sm">
          <Button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            ← Newer
          </Button>
          <span className="font-data text-faint">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)}{' '}
            of {data.total}
          </span>
          <Button onClick={() => setPage((p) => p + 1)} disabled={!data.has_more}>
            Older →
          </Button>
        </div>
      )}
    </div>
  )
}
