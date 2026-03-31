import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../../api/dashboard'
import CacheAge from '../ui/CacheAge'
import Spinner from '../ui/Spinner'

// ── Slot config ────────────────────────────────────────────────────────────────

const SLOT_ORDER = ['C', '1B', '2B', '3B', 'SS', 'OF', 'Util', 'SP', 'RP', 'P', 'BN', 'IL', 'IL+', 'IL60', 'DL', 'NA']

const SLOT_ROW_STYLE: Record<string, string> = {
  C:    'bg-blue-50',
  '1B': 'bg-blue-50',
  '2B': 'bg-blue-50',
  '3B': 'bg-blue-50',
  SS:   'bg-blue-50',
  OF:   'bg-cyan-50',
  Util: 'bg-purple-50',
  SP:   'bg-green-50',
  RP:   'bg-lime-50',
  P:    'bg-emerald-50',
  BN:   '',
  IL:   'bg-red-50',
  'IL+':'bg-red-50',
  IL60: 'bg-red-50',
  DL:   'bg-red-50',
  NA:   'bg-yellow-50',
}

const SLOT_LABEL_STYLE: Record<string, string> = {
  C:    'bg-blue-100 text-blue-800',
  '1B': 'bg-blue-100 text-blue-800',
  '2B': 'bg-blue-100 text-blue-800',
  '3B': 'bg-blue-100 text-blue-800',
  SS:   'bg-blue-100 text-blue-800',
  OF:   'bg-cyan-100 text-cyan-800',
  Util: 'bg-purple-100 text-purple-800',
  SP:   'bg-green-100 text-green-800',
  RP:   'bg-lime-100 text-lime-800',
  P:    'bg-emerald-100 text-emerald-800',
  BN:   'bg-gray-100 text-gray-600',
  IL:   'bg-red-100 text-red-700',
  'IL+':'bg-red-100 text-red-700',
  IL60: 'bg-red-100 text-red-700',
  DL:   'bg-red-100 text-red-700',
  NA:   'bg-yellow-100 text-yellow-700',
}

function baseSlot(slot: string): string {
  return slot.replace(/_\d+$/, '')
}

function slotPriority(slot: string): number {
  const base = baseSlot(slot)
  const i = SLOT_ORDER.indexOf(base)
  // Secondary sort by numeric suffix (BN_1 before BN_2)
  const suffix = parseInt(slot.split('_')[1] ?? '0', 10)
  return (i === -1 ? 98 : i) * 100 + suffix
}

function abbrevTeam(name: string): string {
  return name.replace(/\s+\d+$/, '')
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PlayerMatrixPanel() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['all-rosters'],
    queryFn: () => dashboardApi.getAllRosters(),
    staleTime: 120_000,
  })

  const rosters = data?.rosters
  const teamNames = rosters ? Object.keys(rosters.teams) : []
  const sortedSlots = rosters
    ? [...rosters.slots].sort((a, b) => slotPriority(a) - slotPriority(b))
    : []

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-base">Player Exposure Matrix</h2>
        <CacheAge age={data?.cached_age} onRefresh={() => refetch()} />
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
          <Spinner size="sm" /> Loading rosters...
        </div>
      )}
      {isError && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      {!isLoading && rosters && sortedSlots.length > 0 && (
        <div className="overflow-x-auto">
          <table className="text-xs border-collapse w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="sticky left-0 bg-white z-10 text-left py-1.5 pr-4 font-medium text-gray-500 w-14">
                  Slot
                </th>
                {teamNames.map(t => (
                  <th key={t} className="text-left py-1.5 px-2 font-medium text-gray-700 whitespace-nowrap border-l border-gray-100">
                    {abbrevTeam(t)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedSlots.map(slot => {
                const base = baseSlot(slot)
                const rowBg = SLOT_ROW_STYLE[base] ?? ''
                const labelStyle = SLOT_LABEL_STYLE[base] ?? 'bg-green-100 text-green-800'
                return (
                  <tr key={slot} className={`border-t border-gray-100 hover:brightness-95 ${rowBg}`}>
                    <td className={`sticky left-0 z-10 pr-4 py-1 whitespace-nowrap ${rowBg || 'bg-white'}`}>
                      <span className={`inline-block px-1.5 py-0.5 rounded font-mono font-medium ${labelStyle}`}>
                        {base}
                      </span>
                    </td>
                    {teamNames.map(t => {
                      const player = rosters.teams[t]?.[slot] as string | null
                      return (
                        <td key={t} className="px-2 py-1 border-l border-gray-100 whitespace-nowrap text-gray-800">
                          {player || <span className="text-gray-300">—</span>}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
