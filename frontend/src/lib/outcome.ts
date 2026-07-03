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

/** Classify any outcome as win/loss/draw, mirroring backend stats:
 *  binary results pass through; rank 1 is a win, any other rank a loss. */
export function outcomeClass(outcome: Outcome): 'win' | 'loss' | 'draw' | null {
  if ('result' in outcome && typeof outcome.result === 'string') {
    const r = outcome.result
    return r === 'win' || r === 'loss' || r === 'draw' ? r : null
  }
  if ('rank' in outcome && typeof outcome.rank === 'number') {
    return outcome.rank === 1 ? 'win' : 'loss'
  }
  return null
}
