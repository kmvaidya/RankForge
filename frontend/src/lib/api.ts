import axios from 'axios'

import type {
  AppConfig,
  Game,
  GameHealth,
  LeaderboardEntry,
  Match,
  MatchCreate,
  MatchmakingConstraints,
  MatchmakingResponse,
  MatchUpdateResponse,
  Paginated,
  Player,
  PlayerStats,
  RatingStrategy,
} from './types'

// In dev, Vite proxies /api -> http://localhost:8000. In production set
// VITE_API_URL to the backend origin.
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
})

/** Extract a human-readable message from an API error. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      // FastAPI validation errors
      return detail
        .map((d: { msg?: string }) => d.msg ?? 'Invalid input')
        .join('; ')
    }
    return error.message
  }
  return error instanceof Error ? error.message : 'Something went wrong'
}

// --- Config ---

export const getConfig = async (): Promise<AppConfig> =>
  (await api.get('/config')).data

// --- Games ---

export const listGames = async (): Promise<Paginated<Game>> =>
  (await api.get('/games/', { params: { limit: 100 } })).data

export const createGame = async (body: {
  name: string
  rating_strategy: RatingStrategy
  description?: string
}): Promise<Game> => (await api.post('/games/', body)).data

export const updateGame = async (
  id: number,
  body: { name?: string; description?: string },
): Promise<Game> => (await api.put(`/games/${id}`, body)).data

export const deleteGame = async (id: number): Promise<void> => {
  await api.delete(`/games/${id}`)
}

export const getLeaderboard = async (
  gameId: number,
): Promise<Paginated<LeaderboardEntry>> =>
  (await api.get(`/games/${gameId}/leaderboard`, { params: { limit: 100 } }))
    .data

export const getGameHealth = async (gameId: number): Promise<GameHealth> =>
  (await api.get(`/games/${gameId}/health`)).data

// --- Players ---

export const listPlayers = async (): Promise<Paginated<Player>> =>
  (await api.get('/players/', { params: { limit: 100 } })).data

export const createPlayer = async (name: string): Promise<Player> =>
  (await api.post('/players/', { name })).data

export const getPlayerStats = async (id: number): Promise<PlayerStats> =>
  (await api.get(`/players/${id}/stats`)).data

export const getPlayerMatches = async (
  id: number,
  params: { game_id?: number; limit?: number; sort_order?: 'asc' | 'desc' },
): Promise<Paginated<Match>> =>
  (await api.get(`/players/${id}/matches`, { params })).data

// --- Matches ---

export const listMatches = async (params: {
  game_id?: number
  skip?: number
  limit?: number
}): Promise<Paginated<Match>> =>
  (await api.get('/matches/', { params })).data

export const createMatch = async (body: MatchCreate): Promise<Match> =>
  (await api.post('/matches/', body)).data

export const deleteMatch = async (id: number): Promise<void> => {
  await api.delete(`/matches/${id}`)
}

export const updateMatchMetadata = async (
  id: number,
  expectedVersion: number,
  metadata: Record<string, unknown>,
): Promise<MatchUpdateResponse> =>
  (
    await api.put(`/matches/${id}`, {
      expected_version: expectedVersion,
      match_metadata: metadata,
    })
  ).data

// --- Matchmaking ---

export const generateTeams = async (body: {
  game_id: number
  player_ids: number[]
  team_count?: number
  num_results?: number
  constraints?: MatchmakingConstraints
}): Promise<MatchmakingResponse> =>
  (await api.post('/matchmaking/generate', body)).data
