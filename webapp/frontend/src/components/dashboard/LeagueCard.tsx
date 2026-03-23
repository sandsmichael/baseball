import { Link } from 'react-router-dom'
import type { League } from '../../types'

const SCORING_COLOR: Record<string, string> = {
  categories: 'bg-blue-100 text-blue-700',
  roto: 'bg-purple-100 text-purple-700',
  points: 'bg-orange-100 text-orange-700',
}

export default function LeagueCard({ league }: { league: League }) {
  const scoringStyle = SCORING_COLOR[league.scoring_method] ?? 'bg-gray-100 text-gray-600'
  return (
    <Link
      to={`/league/${league.league_id}`}
      className="card p-4 flex flex-col gap-2 hover:shadow-md hover:border-blue-300 transition-all"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-sm text-gray-900 leading-snug">{league.team_name}</p>
          <p className="text-xs text-gray-500 truncate max-w-[160px]">{league.name}</p>
        </div>
        <span className={`badge shrink-0 ${scoringStyle}`}>{league.scoring_method}</span>
      </div>
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span>{league.num_teams} teams</span>
        <span>·</span>
        <span>ID {league.league_id}</span>
      </div>
      <p className="text-xs text-blue-600 font-medium mt-auto">Manage →</p>
    </Link>
  )
}
