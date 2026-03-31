import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../api/dashboard'
import type { MatchupScore, MatchupStat } from '../api/dashboard'
import NavBar from '../components/ui/NavBar'
import Spinner from '../components/ui/Spinner'
import CacheAge from '../components/ui/CacheAge'

// ─── Shared helpers ──────────────────────────────────────────────────────────

function WinBadge({ my, opp }: { my: string | null; opp: string | null }) {
  if (my == null || opp == null) return null
  const m = parseFloat(my), o = parseFloat(opp)
  if (isNaN(m) || isNaN(o)) return null
  const winning = m > o, tied = m === o
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

// ─── Tile view ───────────────────────────────────────────────────────────────

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

function MatchupCard({ m }: { m: MatchupScore }) {
  const isCat = m.scoring_method === 'categories'
  const myPts = m.my_points != null ? parseFloat(m.my_points) : null
  const oppPts = m.opp_points != null ? parseFloat(m.opp_points) : null
  const winning = myPts != null && oppPts != null && myPts > oppPts
  const trailing = myPts != null && oppPts != null && myPts < oppPts

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Week {m.week}</span>
            <WinBadge my={m.my_points} opp={m.opp_points} />
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="font-semibold text-blue-700">{m.my_team}</span>
            <span className="text-gray-400 text-xs">vs</span>
            <span className="font-medium text-gray-700">{m.opponent}</span>
          </div>
          <div className="text-xs text-gray-400 mt-0.5">{m.start} → {m.end}</div>
        </div>
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

function TileView({ matchups }: { matchups: MatchupScore[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {matchups.map((m, i) => <MatchupCard key={i} m={m} />)}
    </div>
  )
}

// ─── Table view ──────────────────────────────────────────────────────────────

function TableView({ matchups }: { matchups: MatchupScore[] }) {
  // Group by scoring_method
  const groups: Record<string, MatchupScore[]> = {}
  for (const m of matchups) {
    const key = m.scoring_method || 'other'
    if (!groups[key]) groups[key] = []
    groups[key].push(m)
  }

  const order = ['categories', 'roto', 'points']
  const sorted = Object.keys(groups).sort((a, b) => {
    const ai = order.indexOf(a), bi = order.indexOf(b)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })

  return (
    <div className="space-y-8">
      {sorted.map(method => (
        <ScoringTable key={method} method={method} matchups={groups[method]} />
      ))}
    </div>
  )
}

function ScoringTable({ method, matchups }: { method: string; matchups: MatchupScore[] }) {
  // Collect ordered stat names from first matchup that has stats
  const sample = matchups.find(m => m.stats.length > 0)
  const statNames = sample ? sample.stats.map(s => s.name) : []
  const isPoints = method === 'points'

  const label = method.charAt(0).toUpperCase() + method.slice(1)

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-700 mb-3 flex items-center gap-2">
        <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-sm font-bold uppercase tracking-wide">{label}</span>
        <span className="text-gray-400 text-sm font-normal">{matchups.length} leagues</span>
      </h2>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="text-left px-3 py-2 font-medium text-gray-500 whitespace-nowrap">League</th>
              <th className="text-left px-3 py-2 font-medium text-gray-500 whitespace-nowrap">My Team</th>
              {isPoints ? (
                <th className="text-center px-3 py-2 font-medium text-gray-500 whitespace-nowrap">Score</th>
              ) : (
                <th className="text-center px-3 py-2 font-medium text-gray-500 whitespace-nowrap">W – L</th>
              )}
              <th className="text-left px-3 py-2 font-medium text-gray-500 whitespace-nowrap">Opponent</th>
              {statNames.map(name => (
                <th key={name} className="text-center px-2 py-2 font-medium text-gray-500 whitespace-nowrap">{name}</th>
              ))}
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {matchups.map((m, i) => {
              const myPts = m.my_points != null ? parseFloat(m.my_points) : null
              const oppPts = m.opp_points != null ? parseFloat(m.opp_points) : null
              const winning = myPts != null && oppPts != null && myPts > oppPts
              const trailing = myPts != null && oppPts != null && myPts < oppPts
              const tied = myPts != null && oppPts != null && myPts === oppPts

              // Build a stat map by name for this matchup
              const statMap: Record<string, MatchupStat> = {}
              for (const s of m.stats) statMap[s.name] = s

              return (
                <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                  {/* League */}
                  <td className="px-3 py-2 font-medium text-gray-800 whitespace-nowrap">{m.league}</td>
                  {/* My team */}
                  <td className="px-3 py-2 text-blue-700 font-medium whitespace-nowrap">{m.my_team}</td>
                  {/* Score */}
                  <td className="px-3 py-2 text-center whitespace-nowrap">
                    {myPts != null && oppPts != null ? (
                      <span className={`font-bold tabular-nums ${
                        winning ? 'text-green-700' : trailing ? 'text-red-600' : 'text-gray-500'
                      }`}>
                        {isPoints ? myPts.toFixed(1) : myPts} – {isPoints ? oppPts.toFixed(1) : oppPts}
                      </span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  {/* Opponent */}
                  <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{m.opponent}</td>
                  {/* Per-stat cells */}
                  {statNames.map(name => {
                    const s = statMap[name]
                    if (!s) return <td key={name} className="px-2 py-2 text-center text-gray-300">—</td>
                    return (
                      <td key={name} className="px-2 py-2 text-center whitespace-nowrap">
                        <span className={`font-mono text-xs ${s.winning === 'me' ? 'text-green-700 font-bold' : s.winning === 'them' ? 'text-red-500' : 'text-gray-600'}`}>
                          {s.mine || '—'}
                        </span>
                        <span className="text-gray-300 mx-0.5">/</span>
                        <span className={`font-mono text-xs ${s.winning === 'them' ? 'text-green-700 font-bold' : s.winning === 'me' ? 'text-red-500' : 'text-gray-600'}`}>
                          {s.theirs || '—'}
                        </span>
                      </td>
                    )
                  })}
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <Link to={`/league/${m.league_id}`} className="text-xs text-blue-600 hover:underline">
                      Manage →
                    </Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MatchupsPage() {
  const [view, setView] = useState<'tile' | 'table'>('tile')

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
          <div className="flex items-center gap-3">
            {/* View toggle */}
            <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white text-sm">
              <button
                onClick={() => setView('tile')}
                className={`px-3 py-1.5 font-medium transition-colors ${view === 'tile' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'}`}
              >
                Tile
              </button>
              <button
                onClick={() => setView('table')}
                className={`px-3 py-1.5 font-medium transition-colors border-l border-gray-200 ${view === 'table' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'}`}
              >
                Table
              </button>
            </div>
            <CacheAge age={data?.cached_age} onRefresh={() => refetch()} />
          </div>
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

        {!isLoading && matchups.length > 0 && (
          view === 'tile'
            ? <TileView matchups={matchups} />
            : <TableView matchups={matchups} />
        )}
      </main>
    </div>
  )
}
