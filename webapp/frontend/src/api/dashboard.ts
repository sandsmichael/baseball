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

  getILOverflow: (refresh = false) =>
    api.get<{ candidates: ILCandidate[]; cached_age: number | null }>(
      `/dashboard/il-overflow${refresh ? '?refresh=true' : ''}`
    ),

  getBenchedStarters: (refresh = false) =>
    api.get<{ candidates: BenchedStarter[]; cached_age: number | null }>(
      `/dashboard/benched-starters${refresh ? '?refresh=true' : ''}`
    ),

  getMatchupScores: (refresh = false) =>
    api.get<{ matchups: MatchupScore[]; cached_age: number | null }>(
      `/dashboard/matchup-scores${refresh ? '?refresh=true' : ''}`
    ),

  getLineupScratches: (refresh = false) =>
    api.get<{ candidates: LineupScratch[]; cached_age: number | null }>(
      `/dashboard/lineup-scratches${refresh ? '?refresh=true' : ''}`
    ),

  autoStartPitchers: (days = 6) =>
    api.post<{ results: AutoStartResult[]; total: number }>(
      `/dashboard/auto-start-pitchers?days=${days}`, {}
    ),
}

export interface AutoStartResult {
  date: string
  league: string
  my_team: string
  started: string | null
  started_from: string | null
  benched: string | null
  benched_from: string | null
  status: 'ok' | 'error'
  error: string | null
}

export interface MatchupStat {
  stat_id: string
  name: string
  sort_order: number
  mine: string
  theirs: string
  winning: 'me' | 'them' | 'tie' | null
}

export interface MatchupScore {
  league: string
  league_id: string
  my_team: string
  opponent: string
  week: string | number
  start: string
  end: string
  status: string
  scoring_method: string
  my_points: string | null
  opp_points: string | null
  stats: MatchupStat[]
}

export interface BenchedStarter {
  league: string
  my_team: string
  name: string
  mlb_team: string
  positions: string
  status: string
  slot: string
  player_key: string
  probable: boolean
}

export interface LineupScratch {
  league: string
  my_team: string
  name: string
  mlb_team: string
  positions: string
  slot: string
  player_key: string
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
