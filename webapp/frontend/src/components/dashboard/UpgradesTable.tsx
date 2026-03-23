import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { dashboardApi } from '../../api/dashboard'
import CacheAge from '../ui/CacheAge'
import Spinner from '../ui/Spinner'
import type { UpgradeCandidate } from '../../types'

const PROJ_SYSTEMS = ['steamerr', 'atc', 'zips', 'thebat', 'thebatx']

function fmt(v: number | null | undefined) {
  if (v == null) return '—'
  return v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)
}

function fmtScore(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toFixed(2)
}

export default function UpgradesTable() {
  const [projSystem, setProjSystem] = useState('steamerr')
  const [n] = useState(5)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['upgrades', n, projSystem],
    queryFn: () => dashboardApi.getUpgrades(n, projSystem),
    staleTime: 600_000,
  })

  const upgrades = data?.upgrades ?? []

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="font-semibold text-base">
          Upgrade Candidates
          {upgrades.length > 0 && (
            <span className="ml-2 text-sm text-gray-500 font-normal">({upgrades.length})</span>
          )}
        </h2>
        <div className="flex items-center gap-3">
          <select
            value={projSystem}
            onChange={(e) => setProjSystem(e.target.value)}
            className="text-xs border rounded px-2 py-1 text-gray-600"
          >
            {PROJ_SYSTEMS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <CacheAge age={data?.cached_age} onRefresh={() => refetch()} />
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
          <Spinner size="sm" />
          Analyzing all leagues... this may take up to 90 seconds
        </div>
      )}
      {isError && (
        <p className="text-sm text-red-500">Error: {String(error)}</p>
      )}
      {!isLoading && !isError && upgrades.length === 0 && (
        <p className="text-sm text-gray-500 py-2">No upgrade opportunities found.</p>
      )}
      {!isLoading && upgrades.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-gray-500">
                <th className="text-left py-1.5 font-medium">Available</th>
                <th className="text-right py-1.5 font-medium">Curr</th>
                <th className="text-right py-1.5 font-medium">Proj</th>
                <th className="text-left py-1.5 font-medium px-2">vs. Rostered</th>
                <th className="text-right py-1.5 font-medium">Curr △</th>
                <th className="text-right py-1.5 font-medium">Proj △</th>
                <th className="text-left py-1.5 font-medium">Slot</th>
                <th className="text-left py-1.5 font-medium">League</th>
              </tr>
            </thead>
            <tbody>
              {upgrades.slice(0, 50).map((u: UpgradeCandidate, i: number) => (
                <tr key={i} className="table-row-hover border-b last:border-0">
                  <td className="py-1.5 font-medium">{u.available}</td>
                  <td className="py-1.5 text-right text-gray-600">{fmtScore(u.avail_curr_score)}</td>
                  <td className="py-1.5 text-right text-gray-600">{fmtScore(u.avail_proj_score)}</td>
                  <td className="py-1.5 px-2 text-gray-500">{u.rostered}</td>
                  <td className={`py-1.5 text-right font-medium ${u.curr_improvement != null && u.curr_improvement > 0 ? 'text-green-600' : 'text-gray-400'}`}>
                    {fmt(u.curr_improvement)}
                  </td>
                  <td className={`py-1.5 text-right font-medium ${u.proj_improvement != null && u.proj_improvement > 0 ? 'text-green-600' : 'text-gray-400'}`}>
                    {fmt(u.proj_improvement)}
                  </td>
                  <td className="py-1.5 text-xs text-gray-500">{u.rostered_slot}</td>
                  <td className="py-1.5 text-xs text-gray-400 max-w-[120px] truncate">{u.my_team}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {upgrades.length > 50 && (
            <p className="text-xs text-gray-400 mt-2">Showing top 50 of {upgrades.length}</p>
          )}
        </div>
      )}
    </div>
  )
}
