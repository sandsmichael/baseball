import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../api/dashboard'
import type { MatchupScore, MatchupStat } from '../api/dashboard'
import NavBar from '../components/ui/NavBar'
import Spinner from '../components/ui/Spinner'
import CacheAge from '../components/ui/CacheAge'

function WinBadge({ my, opp }: { my: string | null; opp: string | null }) {
  if (my == null || opp == null) return null
  const m = parseFloat(my), o = parseFloat(opp)
  if (isNaN(m) || isNaN(o)) return null
  const winning = m > o
  const tied = m === o
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
      tied    ? 'bg-gray-100 text-gray-500' :
      winning ? 'bg-green-100 text-green-700' :
                'bg-red-100 text-red-600'
    }`}>
      {tied ? 'TIED' : winning ? 'WINNING' : 'TRAILING'}
    </span>
  )
}

function StatRow({ stat }: { stat: MatchupStat }) {
  const w = stat.winning
  return (
    <tr className="border-b last:border-0 text-sm">
      <td className="py-1 text-xs font-medium text-gray-500 w-16">{stat.name}</td>
      <td className={`py-1 text-right pr-3 font-mono ${w === 'me' ? 'text-green-700 font-bold' : w === 'them' ? 'text-red-500' : 'text-gray-700'}`}>
        {stat.mine || '—'}
      </td>
      <td className={`py-1 text-left pl-3 font-mono ${w === 'them' ? 'text-green-700 font-bold' : w === 'me' ? 'text-red-500' : 'text-gray-700'}`}>
        {stat.theirs || '—'}
      </td>
    </tr>
  )
}

function MatchupCard({ m, onRefresh }: { m: MatchupScore; onRefresh: () => void }) {
  const isCat = m.scoring_method === 'categories'
  const myPts = m.my_points != null ? parseFloat(m.my_points) : null
  const oppPts = m.opp_points != null ? parseFloat(m.opp_points) : null
  const winning = myPts != null && oppPts != null && myPts > oppPts
  const trailing = myPts != null && oppPts != null && myPts < oppPts
  const tied = myPts != null && oppPts != null && myPts === oppPts

  return (
    <div className="card p-4">
      {/* Card header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              Week {m.week}
            </span>
            <WinBadge my={m.my_points} opp={m.opp_points} />
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="font-semibold text-blue-700">{m.my_team}</span>
            <span className="text-gray-400 text-xs">vs</span>
            <span className="font-medium text-gray-700">{m.opponent}</span>
          </div>
          <div className="text-xs text-gray-400 mt-0.5">{m.start} → {m.end}</div>
        </div>
        {/* Score summary */}
        <div className="text-right shrink-0 ml-4">
          {myPts != null && oppPts != null ? (
            <div className="text-lg font-bold tabular-nums">
              <span className={winning ? 'text-green-700' : trailing ? 'text-red-600' : 'text-gray-600'}>
                {isCat ? myPts : myPts.toFixed(1)}
              </span>
              <span className="text-gray-300 mx-1">–</span>
              <span className={trailing ? 'text-green-700' : winning ? 'text-red-600' : 'text-gray-600'}>
                {isCat ? oppPts : oppPts.toFixed(1)}
              </span>
            </div>
          ) : (
            <span className="text-xs text-gray-400">No score yet</span>
          )}
          {isCat && <div className="text-xs text-gray-400">categories</div>}
        </div>
      </div>

      {/* Stat breakdown table */}
      {m.stats.length > 0 && (
        <div className="mt-2">
          <table className="w-full">
            <thead>
              <tr className="text-xs text-gray-400 border-b">
                <th className="text-left pb-1 font-medium w-16">Stat</th>
                <th className="text-right pb-1 pr-3 font-medium text-blue-600">{m.my_team.split(' ').slice(0, -1).join(' ') || m.my_team}</th>
                <th className="text-left pb-1 pl-3 font-medium text-gray-500">{m.opponent.split(' ').slice(0, -1).join(' ') || m.opponent}</th>
              </tr>
            </thead>
            <tbody>
              {m.stats.map(stat => <StatRow key={stat.stat_id} stat={stat} />)}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-3 flex justify-end">
        <Link to={`/league/${m.league_id}`} className="text-xs text-blue-600 hover:underline">
          Manage {m.league} →
        </Link>
      </div>
    </div>
  )
}

export default function MatchupsPage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['matchup-scores'],
    queryFn: () => dashboardApi.getMatchupScores(),
    staleTime: 300_000,
  })

  const matchups = data?.matchups ?? []

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <main className="max-w-screen-xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Matchup Scores</h1>
            <p className="text-sm text-gray-500">Current week across all leagues</p>
          </div>
          <CacheAge age={data?.cached_age} onRefresh={() => refetch()} />
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-gray-500 py-10 justify-center">
            <Spinner /> Loading matchup scores...
          </div>
        )}
        {isError && (
          <p className="text-red-500 text-sm">Error: {String(error)}</p>
        )}

        {!isLoading && matchups.length === 0 && !isError && (
          <p className="text-gray-500 text-sm py-10 text-center">No matchups found.</p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {matchups.map((m, i) => (
            <MatchupCard key={i} m={m} onRefresh={() => refetch()} />
          ))}
        </div>
      </main>
    </div>
  )
}
