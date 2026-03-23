import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { playersApi, type PlayerLookupResult, type PlayerAvailability, type PlayerSuggestion, type StatDict } from '../api/players'
import StatusBadge from '../components/ui/StatusBadge'
import Spinner from '../components/ui/Spinner'

const SYSTEM_LABELS: Record<string, string> = {
  steamer:  'Steamer',
  steamerr: 'Steamer ROS',
  atc:      'ATC',
  zips:     'ZiPS',
  thebat:   'The BAT',
  thebatx:  'The BAT X',
}

// ── Number formatting ──────────────────────────────────────────────────────────

const DEC2 = new Set(['AVG','OBP','SLG','ERA','WHIP','FIP','xERA','K/9','BB/9','HR/9','BB%','K%'])
const DEC1 = new Set(['WAR','wRC+','OPS','IP','EV','Barrel%','HardHit%'])

function fmt(v: number | string | null | undefined, col: string): string {
  if (v == null) return '—'
  const n = Number(v)
  if (isNaN(n)) return String(v)
  if (DEC2.has(col)) return n.toFixed(2)
  if (DEC1.has(col)) return n.toFixed(1)
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

// ── Stat tables ────────────────────────────────────────────────────────────────

const BAT_STAT_COLS = ['G','PA','AB','H','HR','RBI','R','SB','AVG','OBP','SLG','OPS','wRC+','WAR','BB%','K%','EV','Barrel%','HardHit%']
const PIT_STAT_COLS = ['G','GS','IP','W','L','SV','HLD','SO','BB','ERA','WHIP','FIP','xERA','K/9','BB/9']
const BAT_PROJ_COLS = ['PA','AB','H','HR','RBI','R','SB','AVG','OBP','SLG','OPS','wRC+','BB%','K%']
const PIT_PROJ_COLS = ['IP','W','L','SV','HLD','SO','BB','ERA','WHIP','FIP','K/9','BB/9']

function pickCols(data: StatDict[], allCols: string[]): string[] {
  return allCols.filter(c => data.some(d => d[c] != null))
}

interface StatRowProps { label: string; data: StatDict; cols: string[]; highlight?: string }
function StatRow({ label, data, cols, highlight }: StatRowProps) {
  const base = 'border-b last:border-0 text-sm'
  const bg = highlight === 'composite'
    ? 'bg-blue-50 font-semibold'
    : highlight === 'current'
    ? 'bg-green-50 font-medium'
    : ''
  return (
    <tr className={`${base} ${bg} hover:bg-opacity-80`}>
      <td className="py-1.5 pr-4 text-xs whitespace-nowrap font-medium text-gray-600 sticky left-0 bg-white"
          style={highlight === 'composite' ? { background: '#eff6ff' } : highlight === 'current' ? { background: '#f0fdf4' } : {}}>
        {label}
      </td>
      {cols.map(c => (
        <td key={c} className="py-1.5 px-2 text-right tabular-nums text-gray-800">
          {fmt(data[c], c)}
        </td>
      ))}
    </tr>
  )
}

function SectionTable({
  title,
  rows,
  cols,
  allCols,
  highlightRow,
}: {
  title: string
  rows: { label: string; data: StatDict; highlight?: string }[]
  cols?: string[]
  allCols: string[]
  highlightRow?: string
}) {
  const activeCols = cols ?? pickCols(rows.map(r => r.data), allCols)
  if (activeCols.length === 0 || rows.length === 0) return null

  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">{title}</h3>
      <div className="overflow-x-auto rounded border border-gray-200">
        <table className="text-sm w-auto min-w-full">
          <thead>
            <tr className="bg-gray-50 border-b text-xs text-gray-500">
              <th className="text-left py-2 pr-4 font-medium sticky left-0 bg-gray-50 whitespace-nowrap">Source</th>
              {activeCols.map(c => (
                <th key={c} className="text-right py-2 px-2 font-medium whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <StatRow key={i} label={r.label} data={r.data} cols={activeCols} highlight={r.highlight} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Availability grid ──────────────────────────────────────────────────────────

const AVAIL_STYLE: Record<string, string> = {
  fa:      'bg-green-100 text-green-800 font-semibold',
  waivers: 'bg-blue-100 text-blue-800 font-semibold',
  mine:    'bg-purple-100 text-purple-800 font-semibold',
  owned:   'bg-gray-100 text-gray-500',
}
const AVAIL_LABEL_MAP: Record<string, string> = {
  fa:      'Free Agent',
  waivers: 'Waivers',
  mine:    'Mine ★',
  owned:   '',
}

function AvailabilityGrid({ availability }: { availability: PlayerAvailability[] }) {
  const available = availability.filter(a => a.avail_status === 'fa' || a.avail_status === 'waivers')
  const mine      = availability.filter(a => a.avail_status === 'mine')

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-sm items-center">
        <span className="font-medium text-gray-600">
          Available in <strong>{available.length}</strong> of {availability.length} leagues
        </span>
        {mine.length > 0 && <span className="badge bg-purple-100 text-purple-800">You own in {mine.length}</span>}
        {available.length > 0 && <span className="badge bg-green-100 text-green-800">Available in {available.length}</span>}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-gray-500">
            <th className="text-left py-1.5 font-medium">League</th>
            <th className="text-left py-1.5 font-medium">Your Team</th>
            <th className="text-left py-1.5 font-medium">Status</th>
            <th className="text-left py-1.5 font-medium">Owner</th>
          </tr>
        </thead>
        <tbody>
          {availability.map((a, i) => (
            <tr key={i} className={`border-b last:border-0 hover:bg-gray-50 ${
              a.avail_status === 'mine' ? 'bg-purple-50' : a.available ? 'bg-green-50' : ''
            }`}>
              <td className="py-1.5">
                <Link to={`/league/${a.league_id}`} className="text-blue-600 hover:underline text-xs">
                  {a.league_name.replace(/Yahoo Prize |Yahoo /g, '').trim()}
                </Link>
              </td>
              <td className="py-1.5 text-xs text-gray-500">{a.my_team}</td>
              <td className="py-1.5">
                <span className={`badge ${AVAIL_STYLE[a.avail_status]}`}>
                  {AVAIL_LABEL_MAP[a.avail_status] || a.label}
                </span>
              </td>
              <td className="py-1.5 text-xs text-gray-600">
                {(a.avail_status === 'owned' || a.avail_status === 'mine') ? a.label : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Player result view ─────────────────────────────────────────────────────────

function PlayerResult({ data }: { data: PlayerLookupResult }) {
  const p = data.player
  const isPit = data.is_pitcher
  const statCols = isPit ? PIT_STAT_COLS : BAT_STAT_COLS
  const projCols = isPit ? PIT_PROJ_COLS : BAT_PROJ_COLS

  // Season stats rows
  const seasonRows: { label: string; data: StatDict; highlight?: string }[] = []
  if (Object.keys(data.current_stats).length > 0) {
    seasonRows.push({ label: `${new Date().getFullYear()} (Current)`, data: data.current_stats, highlight: 'current' })
  }
  for (const h of data.historical_stats) {
    seasonRows.push({ label: String(h.season), data: h.stats })
  }

  // Projection rows
  const projRows: { label: string; data: StatDict; highlight?: string }[] = []
  for (const [sys, vals] of Object.entries(data.projections_by_system)) {
    projRows.push({ label: SYSTEM_LABELS[sys] ?? sys, data: vals })
  }
  if (Object.keys(data.composite_projection).length > 0) {
    projRows.push({ label: 'Composite Avg', data: data.composite_projection, highlight: 'composite' })
  }

  return (
    <div className="space-y-5">
      {/* Player header */}
      <div className="card p-5">
        <div className="flex items-center gap-4 mb-5">
          {p.headshot_url && (
            <img src={p.headshot_url} alt={p.name}
              className="w-16 h-16 rounded-full object-cover bg-gray-100 border shrink-0"
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          )}
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-2xl font-bold">{p.name}</h2>
              <StatusBadge status={p.status} />
            </div>
            <p className="text-gray-500 text-sm mt-0.5">{p.team} · {p.positions}</p>
          </div>
        </div>

        {/* Season Stats */}
        {seasonRows.length === 0 && projRows.length === 0 && (
          <p className="text-sm text-gray-400 italic">No stats available yet for this season.</p>
        )}
        {seasonRows.length > 0 && (
          <SectionTable
            title="Season Stats"
            rows={seasonRows}
            allCols={statCols}
          />
        )}
        {projRows.length > 0 && (
          <SectionTable
            title="Projections"
            rows={projRows}
            allCols={projCols}
          />
        )}
        {seasonRows.length === 0 && projRows.length > 0 && (
          <p className="text-xs text-gray-400 mb-4 italic">Current season stats not yet available.</p>
        )}
      </div>

      {/* Availability */}
      <div className="card p-5">
        <h3 className="text-base font-semibold mb-4">Availability Across Your Leagues</h3>
        <AvailabilityGrid availability={data.availability} />
      </div>
    </div>
  )
}

// ── Autocomplete input ─────────────────────────────────────────────────────────

function PlayerSearch({ onSelect }: { onSelect: (name: string) => void }) {
  const [input, setInput] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  // Debounce
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(input), 300)
    return () => clearTimeout(t)
  }, [input])

  const { data: suggestions, isFetching } = useQuery({
    queryKey: ['autocomplete', debouncedQ],
    queryFn: () => playersApi.autocomplete(debouncedQ),
    enabled: debouncedQ.length >= 2,
    staleTime: 30_000,
  })

  const players = suggestions?.players ?? []

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function pick(p: PlayerSuggestion) {
    setInput(p.name)
    setOpen(false)
    onSelect(p.name)
  }

  function handleSubmit() {
    if (input.trim().length >= 2) {
      setOpen(false)
      onSelect(input.trim())
    }
  }

  const showDropdown = open && debouncedQ.length >= 2 && (isFetching || players.length > 0)

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex gap-2">
        <input
          className="flex-1 border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="Player name (e.g. Zack, Tucker, Ohtani...)"
          value={input}
          autoFocus
          onChange={e => { setInput(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleSubmit()
            if (e.key === 'Escape') setOpen(false)
          }}
        />
        <button
          className="btn-primary px-5 py-2.5"
          onClick={handleSubmit}
          disabled={input.trim().length < 2}
        >
          Search
        </button>
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-y-auto">
          {isFetching && players.length === 0 && (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-gray-400">
              <Spinner size="sm" /> Searching...
            </div>
          )}
          {players.map((p, i) => (
            <button
              key={i}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-blue-50 text-left transition-colors"
              onMouseDown={e => { e.preventDefault(); pick(p) }}
            >
              {p.headshot_url ? (
                <img src={p.headshot_url} alt="" className="w-8 h-8 rounded-full object-cover bg-gray-100 shrink-0"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              ) : (
                <div className="w-8 h-8 rounded-full bg-gray-200 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <span className="font-medium text-sm">{p.name}</span>
                <span className="text-xs text-gray-400 ml-2">{p.team} · {p.positions}</span>
              </div>
              {p.status && <StatusBadge status={p.status} />}
            </button>
          ))}
          {!isFetching && players.length === 0 && debouncedQ.length >= 2 && (
            <div className="px-4 py-3 text-sm text-gray-400">No players found for "{debouncedQ}"</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function PlayersPage() {
  const [query, setQuery] = useState('')

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['player-lookup', query],
    queryFn:  () => playersApi.lookup(query),
    enabled:  query.length >= 2,
    staleTime: 60_000,
    retry: false,
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="mb-1">
          <Link to="/" className="text-blue-600 hover:text-blue-700 text-sm">← Dashboard</Link>
        </div>
        <h1 className="text-xl font-bold text-gray-900">Player Lookup</h1>
        <p className="text-xs text-gray-500">Stats, projections &amp; availability across all your leagues</p>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-5">
        {/* Search */}
        <div className="card p-4">
          <PlayerSearch onSelect={setQuery} />
          {isLoading && query && (
            <div className="flex items-center gap-2 text-xs text-gray-400 mt-2">
              <Spinner size="sm" />
              Checking availability across all 10 leagues + fetching stats…
            </div>
          )}
        </div>

        {/* Error */}
        {isError && (
          <div className="card p-4 border-red-200 bg-red-50">
            <p className="text-sm text-red-600">
              {String(error).includes('404') || String(error).includes('not found')
                ? `Player "${query}" not found. Try a different name.`
                : `Error: ${String(error)}`}
            </p>
          </div>
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <div className="card p-5 animate-pulse space-y-3">
            <div className="flex gap-4 items-center">
              <div className="w-16 h-16 rounded-full bg-gray-200" />
              <div className="space-y-2">
                <div className="h-6 w-40 bg-gray-200 rounded" />
                <div className="h-4 w-24 bg-gray-200 rounded" />
              </div>
            </div>
            <div className="h-32 bg-gray-200 rounded" />
          </div>
        )}

        {/* Results */}
        {!isLoading && data && !isError && <PlayerResult data={data} />}

        {/* Empty state */}
        {!query && !data && !isLoading && (
          <div className="text-center py-16 text-gray-400">
            <div className="text-5xl mb-3">🔍</div>
            <p className="text-sm">Start typing a player name above</p>
          </div>
        )}
      </main>
    </div>
  )
}
