import type { Outcome } from './types'

/** Human label for an outcome: 'win' | 'loss' | 'draw' | 'rank N' | ''. */
export function outcomeLabel(outcome: Outcome): string {
  if ('result' in outcome && typeof outcome.result === 'string') {
    return outcome.result
  }
  if ('rank' in outcome && typeof outcome.rank === 'number') {
    return `rank ${outcome.rank}`
  }
  return ''
}
