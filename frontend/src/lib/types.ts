// Types mirroring the RankForge API's Pydantic schemas.

export interface RatingInfo {
  rating: number
  rd: number
  vol: number
}

export interface Player {
  id: number
  name: string
  created_at: string
}

export type RatingStrategy = 'glicko2' | 'dummy'

export interface GameHealth {
  game_id: number
  players: number
  matches: number
  mean_rating: number
  rating_drift: number
}

export interface Game {
  id: number
  name: string
  rating_strategy: RatingStrategy
  description: string | null
  rating_config?: Record<string, unknown>
}

export interface RatingChange {
  rating_change: number
  rd_change: number
  vol_change: number
}

export type Outcome =
  | { result: 'win' | 'loss' | 'draw'; [key: string]: unknown }
  | { rank: number; [key: string]: unknown }

export interface MatchParticipant {
  id: number
  player_id: number
  player: Player
  team_id: number
  outcome: Outcome
  rating_info_before: RatingInfo | null
  rating_info_change: RatingChange | null
}

export interface Match {
  id: number
  game_id: number
  played_at: string
  version: number
  match_metadata: Record<string, unknown>
  participants: MatchParticipant[]
}

export interface Paginated<T> {
  items: T[]
  total: number
  skip: number
  limit: number
  has_more: boolean
}

export interface LeaderboardEntry {
  rank: number
  player: Player
  rating_info: RatingInfo
  stats: Record<string, unknown>
}

export interface GameStats {
  game: Game
  rating_info: RatingInfo
  matches_played: number
  wins: number
  losses: number
  draws: number
  win_rate: number
}

export interface PlayerStats {
  player_id: number
  player_name: string
  total_matches: number
  total_wins: number
  total_losses: number
  total_draws: number
  overall_win_rate: number
  games_played: GameStats[]
}

// --- Matchmaking ---

export interface TeamMember {
  player: Player
  rating: number
  rd: number
}

export interface TeamRating {
  mu: number
  sigma: number
}

export interface TeamConfiguration {
  teams: TeamMember[][]
  team_ratings: TeamRating[]
  fairness: number
  win_probabilities: number[]
}

export interface MatchmakingResponse {
  configurations: TeamConfiguration[]
  method: string
  configurations_evaluated: number
}

export interface MatchmakingConstraints {
  together: number[][]
  apart: number[][]
}

// --- Requests ---

export interface ParticipantCreate {
  player_id: number | null
  team_id: number
  outcome: { result: 'win' | 'loss' | 'draw' } | { rank: number }
}

export interface MatchCreate {
  game_id: number
  played_at?: string
  match_metadata?: Record<string, unknown>
  participants: ParticipantCreate[]
}

export interface RecalculationResult {
  matches_recalculated: number
  players_affected: number
}

export interface MatchUpdateResponse {
  match: Match
  recalculation: RecalculationResult | null
}

export interface Season {
  id: number
  game_id: number
  number: number
  started_at: string
}

export interface SeasonList {
  current_season: number
  items: Season[]
}

export interface ChemistryEntry {
  player_id: number
  player_name: string
  matches: number
  wins: number
  losses: number
  draws: number
  win_rate: number
}

export interface PlayerChemistry {
  player_id: number
  game_id: number
  partners: ChemistryEntry[]
  rivals: ChemistryEntry[]
}

/** Runtime deployment config from GET /config (feature flags etc.). */
export interface AppConfig {
  features: string[]
}
