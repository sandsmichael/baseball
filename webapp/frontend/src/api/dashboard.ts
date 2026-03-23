import { api } from './client'
import type {
  League,
  ILCandidate,
  UpgradeCandidate,
  TopAvailablePlayer,
  AllRosters,
} from '../types'

export const dashboardApi = {
  getLeagues: (refresh = false) =>
    api.get<{ leagues: League[]; cached_age: number | null }>(
      `/leagues${refresh ? '?refresh=true' : ''}`
    ),

  getAllRosters: (refresh = false) =>
    api.get<{ rosters: AllRosters; cached_age: number | null }>(
      `/dashboard/rosters${refresh ? '?refresh=true' : ''}`
    ),

  getILCandidates: (refresh = false) =>
    api.get<{ candidates: ILCandidate[]; cached_age: number | null }>(
      `/dashboard/il-candidates${refresh ? '?refresh=true' : ''}`
    ),

  getDTDCandidates: (refresh = false) =>
    api.get<{ candidates: ILCandidate[]; cached_age: number | null }>(
      `/dashboard/dtd-candidates${refresh ? '?refresh=true' : ''}`
    ),

  getTopAvailable: (n = 5, refresh = false) =>
    api.get<{ players: TopAvailablePlayer[]; cached_age: number | null }>(
      `/dashboard/top-available?n=${n}${refresh ? '&refresh=true' : ''}`
    ),

  getTopAvailableWithStats: (n = 5, refresh = false) =>
    api.get<{ players: TopAvailablePlayer[]; cached_age: number | null }>(
      `/dashboard/top-available-with-stats?n=${n}${refresh ? '&refresh=true' : ''}`
    ),

  getUpgrades: (n = 5, projSystem = 'steamerr', refresh = false) =>
    api.get<{ upgrades: UpgradeCandidate[]; cached_age: number | null }>(
      `/dashboard/upgrades?n=${n}&proj_system=${projSystem}${refresh ? '&refresh=true' : ''}`
    ),

  getEmptySlots: (refresh = false) =>
    api.get<{ empty_slots: EmptySlot[]; cached_age: number | null }>(
      `/dashboard/empty-slots${refresh ? '?refresh=true' : ''}`
    ),
}

export interface EmptySlot {
  league: string
  league_id: string
  my_team: string
  slot: string
  empty_count: number
  filled: number
  expected: number
}
