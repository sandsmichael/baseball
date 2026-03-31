import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../../api/dashboard'
import type { EmptySlot, BenchedStarter, LineupScratch, AutoStartResult } from '../../api/dashboard'
import StatusBadge from '../ui/StatusBadge'
import SlotChip from '../ui/SlotChip'
import CacheAge from '../ui/CacheAge'
import Spinner from '../ui/Spinner'
import type { ILCandidate } from '../../types'

function CandidateTable({ rows, emptyMsg }: { rows: ILCandidate[]; emptyMsg: string }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-500 py-2">{emptyMsg}</p>
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-xs text-gray-500">
          <th className="text-left py-1.5 font-medium">Player</th>
          <th className="text-left py-1.5 font-medium">MLB</th>
          <th className="text-left py-1.5 font-medium">Status</th>
          <th className="text-left py-1.5 font-medium">In Slot</th>
          <th className="text-left py-1.5 font-medium">League</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="table-row-hover border-b last:border-0">
            <td className="py-1.5 font-medium">{r.name}</td>
            <td className="py-1.5 text-gray-600">{r.mlb_team}</td>
            <td className="py-1.5"><StatusBadge status={r.status} /></td>
            <td className="py-1.5"><SlotChip slot={r.slot} /></td>
            <td className="py-1.5 text-xs text-gray-500 max-w-[140px] truncate">{r.my_team}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function AutoStartButton() {
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<AutoStartResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleClick() {
    setRunning(true)
    setResults(null)
    setError(null)
    try {
      const data = await dashboardApi.autoStartPitchers(6)
      setResults(data.results)
    } catch (e: any) {
      setError(e?.message ?? 'Unknown error')
    } finally {
      setRunning(false)
    }
  }

  const swaps = results?.filter(r => r.status === 'ok') ?? []
  const errors = results?.filter(r => r.status === 'error' && r.from_bench) ?? []

  return (
    <div className="mb-5 border border-blue-100 rounded-lg p-3 bg-blue-50">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold text-blue-800">Auto-Start Pitchers</h3>
          <p className="text-xs text-blue-600">Optimise SP slots for the next 6 days across all leagues</p>
        </div>
        <button
          onClick={handleClick}
          disabled={running}
          className="px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {running ? <><Spinner size="sm" /> Running...</> : '⚾ Auto-Start SPs'}
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-600 mt-1">Error: {error}</p>
      )}

      {results !== null && (
        <div className="mt-2 text-xs space-y-0.5">
          {swaps.length === 0 && errors.length === 0 && (
            <p className="text-blue-700">No SP swaps needed — lineups already optimal.</p>
          )}
          {swaps.map((r, i) => (
            <div key={i} className="flex items-center gap-1.5 text-green-700">
              <span className="text-green-500">✓</span>
              <span className="font-medium">{r.league}</span>
              <span className="text-gray-400">[{r.date}]</span>
              <span>{r.from_bench} → SP</span>
              <span className="text-gray-400">·</span>
              <span>{r.to_bench} → BN</span>
            </div>
          ))}
          {errors.map((r, i) => (
            <div key={i} className="flex items-center gap-1.5 text-red-600">
              <span>✕</span>
              <span className="font-medium">{r.league}</span>
              <span className="text-gray-400">[{r.date}]</span>
              <span>{r.from_bench} ↔ {r.to_bench}: {r.error}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AlertPanel() {
  const il = useQuery({
    queryKey: ['il-candidates'],
    queryFn: () => dashboardApi.getILCandidates(),
    staleTime: 120_000,
  })
  const dtd = useQuery({
    queryKey: ['dtd-candidates'],
    queryFn: () => dashboardApi.getDTDCandidates(),
    staleTime: 120_000,
  })
  const emptySlots = useQuery({
    queryKey: ['empty-slots'],
    queryFn: () => dashboardApi.getEmptySlots(),
    staleTime: 300_000,
  })
  const ilOverflow = useQuery({
    queryKey: ['il-overflow'],
    queryFn: () => dashboardApi.getILOverflow(),
    staleTime: 120_000,
  })
  const benchedStarters = useQuery({
    queryKey: ['benched-starters'],
    queryFn: () => dashboardApi.getBenchedStarters(),
    staleTime: 120_000,
  })
  const lineupScratches = useQuery({
    queryKey: ['lineup-scratches'],
    queryFn: () => dashboardApi.getLineupScratches(),
    staleTime: 120_000,
  })

  const ilCount = il.data?.candidates.length ?? 0
  const dtdCount = dtd.data?.candidates.length ?? 0
  const emptyCount = emptySlots.data?.empty_slots.length ?? 0
  const overflowCount = ilOverflow.data?.candidates.length ?? 0
  const benchedCount = benchedStarters.data?.candidates.length ?? 0
  const scratchCount = lineupScratches.data?.candidates.length ?? 0
  const totalAlerts = ilCount + dtdCount + emptyCount + overflowCount + benchedCount + scratchCount

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-base flex items-center gap-2">
          Alerts
          {totalAlerts > 0 && (
            <span className="badge bg-red-500 text-white">{totalAlerts}</span>
          )}
        </h2>
        <div className="flex gap-3">
          <CacheAge
            age={il.data?.cached_age}
            onRefresh={() => {
              il.refetch()
              dtd.refetch()
            }}
          />
        </div>
      </div>

      {/* Auto-Start Pitchers */}
      <AutoStartButton />

      {/* Empty Roster Slots */}
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-orange-700 mb-2 flex items-center gap-1.5">
          Empty Roster Slots
          {emptyCount > 0 && <span className="badge bg-orange-100 text-orange-700">{emptyCount}</span>}
        </h3>
        {emptySlots.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
        ) : emptySlots.isError ? (
          <p className="text-sm text-red-500">Error: {String(emptySlots.error)}</p>
        ) : (emptySlots.data?.empty_slots ?? []).length === 0 ? (
          <p className="text-sm text-gray-500 py-2">All roster spots filled.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-gray-500">
                <th className="text-left py-1.5 font-medium">Slot</th>
                <th className="text-left py-1.5 font-medium">Empty</th>
                <th className="text-left py-1.5 font-medium">Team</th>
                <th className="text-left py-1.5 font-medium">League</th>
                <th className="text-right py-1.5 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {(emptySlots.data?.empty_slots ?? []).map((s: EmptySlot, i: number) => (
                <tr key={i} className="table-row-hover border-b last:border-0">
                  <td className="py-1.5"><SlotChip slot={s.slot} /></td>
                  <td className="py-1.5 text-orange-600 font-medium">{s.empty_count} of {s.expected}</td>
                  <td className="py-1.5 text-gray-600">{s.my_team}</td>
                  <td className="py-1.5 text-xs text-gray-500 max-w-[140px] truncate">{s.league}</td>
                  <td className="py-1.5 text-right">
                    <Link
                      to={`/league/${s.league_id}`}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Manage →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Lineup Scratches — batters in active slots confirmed not starting */}
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-red-700 mb-2 flex items-center gap-1.5">
          Batters Not in Today's Lineup
          {scratchCount > 0 && <span className="badge bg-red-100 text-red-700">{scratchCount}</span>}
        </h3>
        {lineupScratches.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
        ) : lineupScratches.isError ? (
          <p className="text-sm text-red-500">Error: {String(lineupScratches.error)}</p>
        ) : (lineupScratches.data?.candidates ?? []).length === 0 ? (
          <p className="text-sm text-gray-500 py-2">All active batters are in today's lineup.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-gray-500">
                <th className="text-left py-1.5 font-medium">Player</th>
                <th className="text-left py-1.5 font-medium">MLB</th>
                <th className="text-left py-1.5 font-medium">Pos</th>
                <th className="text-left py-1.5 font-medium">Slot</th>
                <th className="text-left py-1.5 font-medium">League</th>
              </tr>
            </thead>
            <tbody>
              {(lineupScratches.data?.candidates ?? []).map((s: LineupScratch, i: number) => (
                <tr key={i} className="table-row-hover border-b last:border-0">
                  <td className="py-1.5 font-medium flex items-center gap-1.5">
                    <span className="text-red-500">✕</span> {s.name}
                  </td>
                  <td className="py-1.5 text-gray-600">{s.mlb_team}</td>
                  <td className="py-1.5 text-gray-600 text-xs">{s.positions}</td>
                  <td className="py-1.5"><SlotChip slot={s.slot} /></td>
                  <td className="py-1.5 text-xs text-gray-500 max-w-[140px] truncate">{s.my_team}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Benched Starters — pitchers with a game today sitting on bench */}
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-green-700 mb-2 flex items-center gap-1.5">
          Pitchers Scheduled Today on Bench
          {benchedCount > 0 && <span className="badge bg-green-100 text-green-700">{benchedCount}</span>}
        </h3>
        {benchedStarters.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
        ) : benchedStarters.isError ? (
          <p className="text-sm text-red-500">Error: {String(benchedStarters.error)}</p>
        ) : (benchedStarters.data?.candidates ?? []).length === 0 ? (
          <p className="text-sm text-gray-500 py-2">No probable starters sitting on bench.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-gray-500">
                <th className="text-left py-1.5 font-medium">Player</th>
                <th className="text-left py-1.5 font-medium">MLB</th>
                <th className="text-left py-1.5 font-medium">Pos</th>
                <th className="text-left py-1.5 font-medium">League</th>
              </tr>
            </thead>
            <tbody>
              {(benchedStarters.data?.candidates ?? []).map((s: BenchedStarter, i: number) => (
                <tr key={i} className="table-row-hover border-b last:border-0">
                  <td className="py-1.5 font-medium flex items-center gap-1.5">{s.name} <span className="text-green-600">✓</span></td>
                  <td className="py-1.5 text-gray-600">{s.mlb_team}</td>
                  <td className="py-1.5 text-gray-600 text-xs">{s.positions}</td>
                  <td className="py-1.5 text-xs text-gray-500 max-w-[140px] truncate">{s.my_team}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* IL Overflow — healthy players stuck in IL slots */}
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-purple-700 mb-2 flex items-center gap-1.5">
          Healthy Players in IL Slot
          {overflowCount > 0 && <span className="badge bg-purple-100 text-purple-700">{overflowCount}</span>}
        </h3>
        {ilOverflow.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
        ) : ilOverflow.isError ? (
          <p className="text-sm text-red-500">Error: {String(ilOverflow.error)}</p>
        ) : (
          <CandidateTable
            rows={ilOverflow.data?.candidates ?? []}
            emptyMsg="No healthy players stuck in IL slots."
          />
        )}
      </div>

      {/* DTD Candidates */}
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-yellow-700 mb-2 flex items-center gap-1.5">
          DTD in Active Slots
          {dtdCount > 0 && <span className="badge bg-yellow-100 text-yellow-700">{dtdCount}</span>}
        </h3>
        {dtd.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
        ) : dtd.isError ? (
          <p className="text-sm text-red-500">Error: {String(dtd.error)}</p>
        ) : (
          <CandidateTable
            rows={dtd.data?.candidates ?? []}
            emptyMsg="No DTD players in active slots."
          />
        )}
      </div>

      {/* IL Candidates */}
      <div>
        <h3 className="text-sm font-semibold text-red-700 mb-2 flex items-center gap-1.5">
          IL Candidates
          {ilCount > 0 && <span className="badge bg-red-100 text-red-700">{ilCount}</span>}
        </h3>
        {il.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
        ) : il.isError ? (
          <p className="text-sm text-red-500">Error: {String(il.error)}</p>
        ) : (
          <CandidateTable
            rows={il.data?.candidates ?? []}
            emptyMsg="No IL candidates — all injured players are correctly slotted."
          />
        )}
      </div>
    </div>
  )
}
