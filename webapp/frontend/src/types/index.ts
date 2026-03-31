export interface League {
  league_id: string
  name: string
  team_name: string
  scoring_method: string
  num_teams: number
  draft_status: string
  league_key: string
}

export interface RosterPlayer {
  slot: string
  name: string
  team: string
  positions: string
  status: string
  player_key: string
}

export interface FreeAgent {
  name: string
  team: string
  positions: string
  status: string
  player_key: string
  pct_owned?: number
}

export interface Standings {
  rank: number
  team: string
  wins: number
  losses: number
  ties: number
  pct: number
  gb: string
}

export interface Matchup {
  week: number
  start: string
  end: string
  you: string
  opponent: string
  opponent_key: string
}

export interface ILCandidate {
  league: string
  my_team: string
  name: string
  mlb_team: string
  positions: string
  status: string
  slot: string
  player_key: string
}

export interface UpgradeCandidate {
  league: string
  my_team: string
  available: string
  avail_curr_score: number | null
  avail_proj_score: number | null
  avail_pct_owned: number
  rostered: string
  rostered_curr_score: number | null
  rostered_proj_score: number | null
  rostered_slot: string
  curr_improvement: number | null
  proj_improvement: number | null
}

export interface TopAvailablePlayer {
  league: string
  my_team: string
  type: 'batter' | 'pitcher'
  rank: number
  name: string
  team: string
  positions: string
  status: string
  pct_owned: number
  // optional stats columns
  PA?: number
  HR?: number
  RBI?: number
  R?: number
  SB?: number
  AVG?: number
  IP?: number
  W?: number
  SV?: number
  SO?: number
  ERA?: number
  WHIP?: number
  [key: string]: unknown
}

export interface AllRosters {
  teams: Record<string, Record<string, string | null>>
  slots: string[]
}

export interface MutationResult {
  success: boolean
  message: string
}
