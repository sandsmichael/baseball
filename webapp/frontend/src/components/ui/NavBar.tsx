import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { dashboardApi } from '../../api/dashboard'
import type { AutoStartResult } from '../../api/dashboard'
import Spinner from './Spinner'

const NAV_LINKS = [
  { to: '/',          label: 'Dashboard'     },
  { to: '/matchups',  label: 'Matchups'      },
  { to: '/players',   label: 'Player Lookup' },
]

function AutoStartDialog({ results, onClose }: { results: AutoStartResult[]; onClose: () => void }) {
  const swaps  = results.filter(r => r.status === 'ok')
  const errors = results.filter(r => r.status === 'error' && r.started)

  // Group swaps by date
  const byDate: Record<string, AutoStartResult[]> = {}
  for (const r of swaps) {
    if (!byDate[r.date]) byDate[r.date] = []
    byDate[r.date].push(r)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div>
            <h2 className="text-base font-bold text-gray-900">Auto-Start Pitchers — Results</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {swaps.length} move{swaps.length !== 1 ? 's' : ''} made
              {errors.length > 0 && ` · ${errors.length} error${errors.length !== 1 ? 's' : ''}`}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">✕</button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-5 py-4 space-y-5">
          {swaps.length === 0 && errors.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-6">
              No SP swaps needed — all lineups already optimal.
            </p>
          )}

          {Object.entries(byDate).sort().map(([d, rows]) => (
            <div key={d}>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">{d}</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-gray-400">
                    <th className="text-left pb-1.5 font-medium">League</th>
                    <th className="text-left pb-1.5 font-medium">Team</th>
                    <th className="text-left pb-1.5 font-medium">Pitcher</th>
                    <th className="text-center pb-1.5 font-medium">From</th>
                    <th className="text-center pb-1.5 font-medium px-2">→</th>
                    <th className="text-center pb-1.5 font-medium">To</th>
                    <th className="text-left pb-1.5 font-medium">Pitcher</th>
                    <th className="text-center pb-1.5 font-medium">From</th>
                    <th className="text-center pb-1.5 font-medium px-2">→</th>
                    <th className="text-center pb-1.5 font-medium">To</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="py-1.5 font-medium text-gray-800 pr-3">{r.league}</td>
                      <td className="py-1.5 text-gray-500 text-xs pr-3">{r.my_team}</td>
                      {/* Started pitcher */}
                      <td className="py-1.5 text-green-700 font-medium pr-2">{r.started}</td>
                      <td className="py-1.5 text-center">
                        <span className="px-1.5 py-0.5 bg-gray-100 rounded text-xs font-mono">{r.started_from}</span>
                      </td>
                      <td className="py-1.5 text-center px-2 text-gray-400">→</td>
                      <td className="py-1.5 text-center">
                        <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-xs font-mono font-bold">SP</span>
                      </td>
                      {/* Benched pitcher */}
                      <td className="py-1.5 text-gray-500 pr-2 pl-4">{r.benched}</td>
                      <td className="py-1.5 text-center">
                        <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-xs font-mono font-bold">{r.benched_from}</span>
                      </td>
                      <td className="py-1.5 text-center px-2 text-gray-400">→</td>
                      <td className="py-1.5 text-center">
                        <span className="px-1.5 py-0.5 bg-gray-100 rounded text-xs font-mono">BN</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {errors.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">Errors</h3>
              {errors.map((r, i) => (
                <div key={i} className="text-xs text-red-600 mb-1">
                  <span className="font-medium">{r.league} [{r.date}]</span> — {r.started} ↔ {r.benched}: {r.error}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium rounded-lg"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

export default function NavBar() {
  const { pathname } = useLocation()
  const [running, setRunning] = useState(false)
  const [dialogResults, setDialogResults] = useState<AutoStartResult[] | null>(null)

  async function handleAutoStart() {
    setRunning(true)
    try {
      const data = await dashboardApi.autoStartPitchers(6)
      setDialogResults(data.results)
    } catch (e: any) {
      setDialogResults([{
        date: new Date().toISOString().slice(0, 10),
        league: 'Error',
        my_team: '',
        started: null,
        started_from: null,
        benched: null,
        benched_from: null,
        status: 'error',
        error: e?.message ?? 'Unknown error',
      }])
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <Link to="/" className="flex items-center gap-2 shrink-0">
          <span className="text-xl">⚾</span>
          <span className="font-bold text-gray-900 text-base hidden sm:block">Fantasy Baseball</span>
        </Link>
        <nav className="flex items-center gap-1">
          {NAV_LINKS.map(({ to, label }) => {
            const active = pathname === to
            return (
              <Link
                key={to}
                to={to}
                className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  active
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                {label}
              </Link>
            )
          })}

          <button
            onClick={handleAutoStart}
            disabled={running}
            className="ml-3 px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {running ? <><Spinner size="sm" /> Starting...</> : '⚡ Auto-Start SPs'}
          </button>
        </nav>
      </header>

      {dialogResults !== null && (
        <AutoStartDialog results={dialogResults} onClose={() => setDialogResults(null)} />
      )}
    </>
  )
}
