import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { dashboardApi } from '../../api/dashboard'
import StatusBadge from '../ui/StatusBadge'
import CacheAge from '../ui/CacheAge'
import Spinner from '../ui/Spinner'
import type { TopAvailablePlayer } from '../../types'

type TabMode = 'basic' | 'stats'

const BAT_COLS = ['PA', 'HR', 'R', 'RBI', 'SB', 'AVG']
const PIT_COLS = ['IP', 'W', 'SV', 'SO', 'ERA', 'WHIP']
const RATE_COLS = new Set(['AVG', 'ERA', 'WHIP'])

function pctHeatmap(pct: number): { bg: string; text: string } {
  const deviation = (pct - 50) / 50  // -1 at 0%, 0 at 50%, +1 at 100%
  const intensity = Math.abs(deviation)
  if (deviation > 0) {
    // Above 50% → green
    const r = Math.round(255 - intensity * (255 - 22))
    const g = Math.round(255 - intensity * (255 - 163))
    const b = Math.round(255 - intensity * (255 - 74))
    return { bg: `rgb(${r},${g},${b})`, text: intensity > 0.5 ? '#fff' : '#166534' }
  } else {
    // Below 50% → red
    const r = Math.round(255 - intensity * (255 - 220))
    const g = Math.round(255 - intensity * 255)
    const b = Math.round(255 - intensity * 255)
    return { bg: `rgb(${r},${g},${b})`, text: intensity > 0.5 ? '#fff' : '#991b1b' }
  }
}

function fmtStat(val: unknown, col: string): string {
  if (val == null) return '—'
  const n = Number(val)
  return isNaN(n) ? '—' : n.toFixed(RATE_COLS.has(col) ? 2 : 0)
}

export default function TopAvailablePanel() {
  const [tab, setTab] = useState<TabMode>('basic')

  const basic = useQuery({
    queryKey: ['top-available', 5],
    queryFn: () => dashboardApi.getTopAvailable(5),
    staleTime: 300_000,
    enabled: tab === 'basic',
  })

  const stats = useQuery({
    queryKey: ['top-available-stats', 5],
    queryFn: () => dashboardApi.getTopAvailableWithStats(5),
    staleTime: 600_000,
    enabled: tab === 'stats',
  })

  const active = tab === 'basic' ? basic : stats
  const players: TopAvailablePlayer[] = active.data?.players ?? []

  const sorted = [...players].sort((a, b) => (b.pct_owned ?? 0) - (a.pct_owned ?? 0))

  const hasBat = sorted.some(p => p.type === 'batter')
  const hasPit = sorted.some(p => p.type === 'pitcher')
  const statCols = tab === 'stats'
    ? [
        ...(hasBat ? BAT_COLS : []),
        ...(hasPit ? PIT_COLS : []),
      ].filter((c, i, arr) => arr.indexOf(c) === i)
    : []
  const visibleStatCols = statCols.filter(c => sorted.some(p => p[c] != null))
  const visibleProjCols = statCols
    .map(c => `proj_${c}`)
    .filter(c => sorted.some(p => p[c] != null))

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="font-semibold text-base">Top Available Players</h2>
        <div className="flex items-center gap-3">
          <div className="flex rounded border overflow-hidden text-xs">
            {(['basic', 'stats'] as TabMode[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1 capitalize transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
              >
                {t === 'basic' ? 'Basic' : 'With Stats'}
              </button>
            ))}
          </div>
          <CacheAge age={active.data?.cached_age} onRefresh={() => active.refetch()} />
        </div>
      </div>

      {active.isLoading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
          <Spinner size="sm" />
          {tab === 'stats' ? 'Fetching stats from FanGraphs...' : 'Loading...'}
        </div>
      )}
      {active.isError && <p className="text-sm text-red-500">Error: {String(active.error)}</p>}

      {!active.isLoading && sorted.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-gray-400">
                <th className="text-left py-1.5 font-medium">Name</th>
                <th className="text-left py-1.5 font-medium">Pos</th>
                <th className="text-left py-1.5 font-medium">Status</th>
                <th className="text-left py-1.5 font-medium">My Team</th>
                <th className="text-left py-1.5 font-medium">League</th>
                <th className="text-right py-1.5 font-medium">%Own</th>
                {visibleStatCols.map(c => (
                  <th key={c} className="text-right py-1.5 font-medium px-1">{c}</th>
                ))}
                {visibleProjCols.map(c => (
                  <th key={c} className="text-right py-1.5 font-medium px-1 text-blue-400">
                    p{c.replace('proj_', '')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((p, i) => (
                <tr key={i} className="border-b last:border-0 hover:bg-gray-50 transition-colors">
                  <td className="py-1.5 font-medium whitespace-nowrap">{p.name}</td>
                  <td className="py-1.5 text-gray-500 whitespace-nowrap">{p.positions}</td>
                  <td className="py-1.5"><StatusBadge status={p.status} /></td>
                  <td className="py-1.5 text-gray-500 whitespace-nowrap">{p.my_team}</td>
                  <td className="py-1.5 text-gray-400 max-w-[120px] truncate">{p.league}</td>
                  <td
                    className="py-1.5 text-right font-medium whitespace-nowrap px-1.5 rounded"
                    style={p.pct_owned != null ? {
                      backgroundColor: pctHeatmap(p.pct_owned).bg,
                      color: pctHeatmap(p.pct_owned).text,
                    } : undefined}
                  >
                    {p.pct_owned != null ? `${p.pct_owned.toFixed(0)}%` : '—'}
                  </td>
                  {visibleStatCols.map(c => (
                    <td key={c} className="py-1.5 text-right text-gray-600 px-1">
                      {fmtStat(p[c], c)}
                    </td>
                  ))}
                  {visibleProjCols.map(c => (
                    <td key={c} className="py-1.5 text-right text-blue-400 px-1">
                      {fmtStat(p[c], c.replace('proj_', ''))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
