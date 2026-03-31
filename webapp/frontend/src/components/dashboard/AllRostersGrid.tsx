import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../../api/dashboard'
import CacheAge from '../ui/CacheAge'
import Spinner from '../ui/Spinner'
import SlotChip from '../ui/SlotChip'

export default function AllRostersGrid() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['all-rosters'],
    queryFn: () => dashboardApi.getAllRosters(),
    staleTime: 120_000,
  })

  const rosters = data?.rosters
  const teams = rosters ? Object.keys(rosters.teams) : []
  const slots = rosters?.slots ?? []

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-base">All Rosters</h2>
        <CacheAge age={data?.cached_age} onRefresh={() => refetch()} />
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
          <Spinner size="sm" /> Loading rosters across all leagues...
        </div>
      )}
      {isError && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      {!isLoading && rosters && teams.length > 0 && (
        <div className="overflow-x-auto">
          <table className="text-xs border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 bg-white z-10 text-left py-1.5 pr-3 font-medium text-gray-500 w-16">Slot</th>
                {teams.map((t) => (
                  <th key={t} className="text-left py-1.5 px-2 font-medium text-gray-700 whitespace-nowrap max-w-[120px] truncate border-l border-gray-100">
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {slots.map((slot) => (
                <tr key={slot} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="sticky left-0 bg-white z-10 pr-3 py-1 whitespace-nowrap">
                    <SlotChip slot={slot.replace(/_\d+$/, '')} />
                  </td>
                  {teams.map((t) => {
                    const player = rosters.teams[t]?.[slot]
                    return (
                      <td key={t} className="px-2 py-1 border-l border-gray-100 whitespace-nowrap text-gray-800">
                        {player || <span className="text-gray-300">—</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
