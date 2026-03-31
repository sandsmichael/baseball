import { api } from './client'

export interface PlayerSuggestion {
  name: string
  team: string
  positions: string
  status: string
  player_key: string
  headshot_url: string
}

export interface PlayerAvailability {
  league_id: string
  league_name: string
  my_team: string
  avail_status: 'fa' | 'waivers' | 'owned' | 'mine'
  label: string
  available: boolean
}

export type StatDict = Record<string, string | number | null>

export interface PlayerLookupResult {
  player: PlayerSuggestion
  is_pitcher: boolean
  fg_id: string | null
  pct_owned: number | null
  availability: PlayerAvailability[]
  current_stats: StatDict
  historical_stats: { season: number; stats: StatDict }[]
  projections_by_system: Record<string, StatDict>
  composite_projection: StatDict
}

export const playersApi = {
  autocomplete: (q: string) =>
    api.get<{ players: PlayerSuggestion[] }>(
      `/players/autocomplete?q=${encodeURIComponent(q)}`
    ),

  lookup: (q: string) =>
    api.get<PlayerLookupResult>(`/players/lookup?q=${encodeURIComponent(q)}`),
}
