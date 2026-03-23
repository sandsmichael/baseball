import type { Matchup, RosterPlayer } from '../../types'
import RosterTable from './RosterTable'

interface Props {
  matchup: Matchup | null
  oppRoster: RosterPlayer[]
  leagueId: string
}

export default function MatchupPanel({ matchup, oppRoster, leagueId }: Props) {
  if (!matchup || !matchup.week) {
    return <p className="text-sm text-gray-500 py-4">No active matchup found.</p>
  }

  return (
    <div className="space-y-6">
      {/* Matchup header */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold">Week {matchup.week}</h3>
          <span className="text-xs text-gray-500">{matchup.start} → {matchup.end}</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="font-medium text-blue-700">{matchup.you}</div>
          <span className="text-gray-400">vs.</span>
          <div className="font-medium text-gray-700">{matchup.opponent}</div>
        </div>
      </div>

      {/* Opponent roster */}
      <div className="card p-4">
        <h3 className="font-semibold mb-4">Opponent: {matchup.opponent}</h3>
        {oppRoster.length === 0 ? (
          <p className="text-sm text-gray-500">No opponent roster available.</p>
        ) : (
          <RosterTable leagueId={leagueId} players={oppRoster} readonly />
        )}
      </div>
    </div>
  )
}
