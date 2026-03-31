import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { leagueApi } from '../../api/league'
import type { AvailablePlayerWithProjections } from '../../api/league'
import StatusBadge from '../ui/StatusBadge'
import Spinner from '../ui/Spinner'
import CacheAge from '../ui/CacheAge'
import ConfirmModal from '../ui/ConfirmModal'
import { useAppStore } from '../../store'
import type { FreeAgent, RosterPlayer } from '../../types'

const POSITIONS = ['All', 'C', '1B', '2B', '3B', 'SS', 'OF', 'SP', 'RP', 'P', 'Util']
const PROJ_SYSTEMS = ['steamer', 'steamerr', 'atc', 'zips', 'thebat', 'thebatx']

const BAT_COLS = ['PA', 'HR', 'RBI', 'R', 'SB', 'AVG', 'OBP', 'SLG', 'OPS', 'wRC+']
const PIT_COLS = ['IP', 'W', 'SV', 'HLD', 'SO', 'ERA', 'WHIP', 'K/9']

interface Props {
  leagueId: string
  roster: RosterPlayer[]
}

function fmt(val: number | null | undefined, col: string): string {
  if (val == null) return '—'
  const rate = ['AVG', 'OBP', 'SLG', 'OPS', 'ERA', 'WHIP', 'K/9', 'BB/9']
  if (rate.includes(col)) return val.toFixed(3)
  return String(Math.round(val))
}

export default function WaiverBrowser({ leagueId, roster }: Props) {
  const qc = useQueryClient()
  const { addToast, removeToast } = useAppStore()
  const [position, setPosition] = useState<string | undefined>(undefined)
  const [mode, setMode] = useState<'waivers' | 'fa' | 'search'>('waivers')
  const [projSystem, setProjSystem] = useState<string>('steamer')
  const [searchQ, setSearchQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [addTarget, setAddTarget] = useState<FreeAgent | AvailablePlayerWithProjections | null>(null)
  const [dropPlayer, setDropPlayer] = useState('')

  const pos = position === 'All' || !position ? undefined : position

  const projQuery = useQuery({
    queryKey: ['avail-proj', leagueId, mode, pos, projSystem],
    queryFn: () => leagueApi.getAvailableWithProjections(leagueId, mode as 'waivers' | 'fa', pos, projSystem, 50),
    staleTime: 120_000,
    enabled: mode !== 'search',
  })

  const searchResults = useQuery({
    queryKey: ['search', leagueId, debouncedQ],
    queryFn: () => leagueApi.searchPlayer(leagueId, debouncedQ),
    enabled: mode === 'search' && debouncedQ.length >= 2,
    staleTime: 0,
  })

  const addMut = useMutation({
    mutationFn: ({ player, drop }: { player: string; drop?: string }) =>
      leagueApi.add(leagueId, player, drop),
    onMutate: ({ player }) => {
      const id = addToast({ type: 'loading', message: `Adding ${player}...` })
      return { id }
    },
    onSuccess: (res, _vars, ctx) => {
      removeToast(ctx!.id)
      addToast({ type: res.success ? 'success' : 'error', message: res.message })
      if (res.success) {
        qc.invalidateQueries({ queryKey: ['roster', leagueId] })
        qc.invalidateQueries({ queryKey: ['avail-proj', leagueId] })
      }
    },
    onError: (err, _vars, ctx) => {
      if (ctx) removeToast(ctx.id)
      addToast({ type: 'error', message: String(err) })
    },
  })

  const isLoading = mode === 'search' ? searchResults.isLoading : projQuery.isLoading
  const projPlayers: AvailablePlayerWithProjections[] = mode === 'search'
    ? (searchResults.data?.players ?? []).map(p => ({ ...p, pct_owned: 0, is_pitcher: false, projections: {} }))
    : (projQuery.data?.players ?? [])

  // Determine which projection columns to show (non-null across players)
  const visibleProjCols = (() => {
    if (mode === 'search' || projPlayers.length === 0) return []
    const hasBat = projPlayers.some(p => !p.is_pitcher)
    const hasPit = projPlayers.some(p => p.is_pitcher)
    const cols = new Set<string>()
    if (hasBat) BAT_COLS.forEach(c => cols.add(c))
    if (hasPit) PIT_COLS.forEach(c => cols.add(c))
    // Keep only columns with at least one non-null value
    return [...cols].filter(c =>
      projPlayers.some(p => p.projections[c] != null)
    )
  })()

  return (
    <div>
      {addTarget && (
        <ConfirmModal
          title={`Add ${addTarget.name}`}
          message={
            dropPlayer
              ? `Add ${addTarget.name} and drop ${dropPlayer}?`
              : `Add ${addTarget.name} to your roster?`
          }
          confirmLabel="Add"
          onConfirm={() => {
            addMut.mutate({ player: addTarget.name, drop: dropPlayer || undefined })
            setAddTarget(null)
            setDropPlayer('')
          }}
          onCancel={() => { setAddTarget(null); setDropPlayer('') }}
        />
      )}

      {/* Controls */}
      <div className="flex flex-wrap gap-2 mb-4">
        {/* Mode toggle */}
        <div className="flex rounded border overflow-hidden text-xs">
          {(['waivers', 'fa', 'search'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 capitalize transition-colors ${mode === m ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            >
              {m === 'fa' ? 'Free Agents' : m === 'search' ? 'Search' : 'Waivers'}
            </button>
          ))}
        </div>

        {/* Projection system */}
        {mode !== 'search' && (
          <select
            className="text-xs border rounded px-2 py-1"
            value={projSystem}
            onChange={e => setProjSystem(e.target.value)}
          >
            {PROJ_SYSTEMS.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}

        {/* Position filter */}
        {mode !== 'search' && (
          <div className="flex flex-wrap gap-1">
            {POSITIONS.map((p) => (
              <button
                key={p}
                onClick={() => setPosition(p === 'All' ? undefined : p)}
                className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                  (position ?? 'All') === p
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        )}

        {/* Search input */}
        {mode === 'search' && (
          <div className="flex gap-2">
            <input
              className="border rounded px-3 py-1 text-sm w-56"
              placeholder="Player name..."
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && setDebouncedQ(searchQ)}
            />
            <button className="btn-primary text-xs" onClick={() => setDebouncedQ(searchQ)}>Search</button>
          </div>
        )}

        {mode !== 'search' && (
          <CacheAge age={projQuery.data?.cached_age} onRefresh={() => projQuery.refetch()} />
        )}
      </div>

      {/* Player list */}
      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-4"><Spinner size="sm" /> Loading...</div>
      )}
      {!isLoading && projPlayers.length === 0 && (
        <p className="text-sm text-gray-500">No players found.</p>
      )}
      {!isLoading && projPlayers.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-gray-500">
                <th className="text-left py-1.5 font-medium">Name</th>
                <th className="text-left py-1.5 font-medium">Team</th>
                <th className="text-left py-1.5 font-medium">Pos</th>
                <th className="text-left py-1.5 font-medium">Status</th>
                {mode !== 'search' && <th className="text-right py-1.5 font-medium">%Own</th>}
                {visibleProjCols.map(c => (
                  <th key={c} className="text-right py-1.5 font-medium px-1">{c}</th>
                ))}
                <th className="text-left py-1.5 font-medium pl-2">Drop</th>
                <th className="text-right py-1.5 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {projPlayers.map((p, i) => (
                <tr key={i} className="table-row-hover border-b last:border-0">
                  <td className="py-1.5 font-medium whitespace-nowrap">{p.name}</td>
                  <td className="py-1.5 text-gray-500">{p.team}</td>
                  <td className="py-1.5 text-gray-500 text-xs whitespace-nowrap">{p.positions}</td>
                  <td className="py-1.5"><StatusBadge status={p.status} /></td>
                  {mode !== 'search' && (
                    <td className="py-1.5 text-right text-xs text-gray-500">
                      {p.pct_owned > 0 ? `${p.pct_owned.toFixed(1)}%` : '—'}
                    </td>
                  )}
                  {visibleProjCols.map(c => (
                    <td key={c} className={`py-1.5 text-right text-xs px-1 ${p.projections[c] == null ? 'text-gray-300' : 'text-gray-700'}`}>
                      {fmt(p.projections[c], c)}
                    </td>
                  ))}
                  <td className="py-1.5 pl-2">
                    <select
                      className="text-xs border rounded px-1 py-0.5 max-w-[130px]"
                      value={addTarget?.name === p.name ? dropPlayer : ''}
                      onChange={(e) => setDropPlayer(e.target.value)}
                      onClick={() => setAddTarget(p)}
                    >
                      <option value="">No drop</option>
                      {roster.map((r) => (
                        <option key={r.player_key} value={r.name}>{r.name}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-1.5 text-right">
                    <button
                      className="btn-primary text-xs py-0.5 px-2"
                      disabled={addMut.isPending}
                      onClick={() => setAddTarget(p)}
                    >
                      Add
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
