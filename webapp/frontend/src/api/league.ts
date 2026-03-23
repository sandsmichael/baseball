import { api } from './client'
import type { RosterPlayer, FreeAgent, Standings, Matchup, MutationResult } from '../types'

export const leagueApi = {
  getRoster: (leagueId: string, refresh = false) =>
    api.get<{ roster: RosterPlayer[]; cached_age: number | null }>(
      `/leagues/${leagueId}/roster${refresh ? '?refresh=true' : ''}`
    ),

  getMatchup: (leagueId: string, refresh = false) =>
    api.get<{ matchup: Matchup; cached_age: number | null }>(
      `/leagues/${leagueId}/matchup${refresh ? '?refresh=true' : ''}`
    ),

  getOpponentRoster: (leagueId: string, refresh = false) =>
    api.get<{ roster: RosterPlayer[]; cached_age: number | null }>(
      `/leagues/${leagueId}/opponent-roster${refresh ? '?refresh=true' : ''}`
    ),

  getStandings: (leagueId: string, refresh = false) =>
    api.get<{ standings: Standings[]; cached_age: number | null }>(
      `/leagues/${leagueId}/standings${refresh ? '?refresh=true' : ''}`
    ),

  getWaivers: (leagueId: string, position?: string, count = 50, refresh = false) => {
    const params = new URLSearchParams({ count: String(count) })
    if (position) params.set('position', position)
    if (refresh) params.set('refresh', 'true')
    return api.get<{ players: FreeAgent[]; cached_age: number | null }>(
      `/leagues/${leagueId}/waivers?${params}`
    )
  },

  getFreeAgents: (leagueId: string, position?: string, count = 50, refresh = false) => {
    const params = new URLSearchParams({ count: String(count) })
    if (position) params.set('position', position)
    if (refresh) params.set('refresh', 'true')
    return api.get<{ players: FreeAgent[]; cached_age: number | null }>(
      `/leagues/${leagueId}/free-agents?${params}`
    )
  },

  searchPlayer: (leagueId: string, q: string) =>
    api.get<{ players: FreeAgent[] }>(`/leagues/${leagueId}/search?q=${encodeURIComponent(q)}`),

  add: (leagueId: string, player: string, drop?: string, faab?: number) =>
    api.post<MutationResult>(`/leagues/${leagueId}/add`, { player, drop, faab }),

  drop: (leagueId: string, player: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/drop`, { player }),

  trade: (leagueId: string, give: string[], receive: string[], team: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/trade`, { give, receive, team }),

  move: (leagueId: string, player: string, position: string, date?: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/move`, { player, position, date }),

  bench: (leagueId: string, player: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/bench`, { player }),

  start: (leagueId: string, player: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/start`, { player }),

  il: (leagueId: string, player: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/il`, { player }),

  swap: (leagueId: string, player1: string, player2: string) =>
    api.post<MutationResult>(`/leagues/${leagueId}/swap`, { player1, player2 }),

  getAvailableWithProjections: (
    leagueId: string,
    mode: 'waivers' | 'fa',
    position: string | undefined,
    projSystem: string,
    count: number,
    refresh = false,
  ) => {
    const params = new URLSearchParams({ mode, proj_system: projSystem, count: String(count) })
    if (position) params.set('position', position)
    if (refresh) params.set('refresh', 'true')
    return api.get<{ players: AvailablePlayerWithProjections[]; cached_age: number | null }>(
      `/leagues/${leagueId}/available-with-projections?${params}`
    )
  },

  getTransactions: (leagueId: string, refresh = false) =>
    api.get<{ transactions: PendingTransaction[]; cached_age: number | null }>(
      `/leagues/${leagueId}/transactions${refresh ? '?refresh=true' : ''}`
    ),
}

export interface AvailablePlayerWithProjections {
  name: string
  team: string
  positions: string
  status: string
  player_key: string
  pct_owned: number
  is_pitcher: boolean
  projections: Record<string, number | null>
}

export interface PendingTransaction {
  type: 'waiver' | 'pending_trade' | string
  status: string
  team_name: string
  date: string
  faab_bid: string | null
  waiver_priority: number | null
  adds: { name: string; team: string; positions: string }[]
  drops: { name: string; team: string; positions: string }[]
}
