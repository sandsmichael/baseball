import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../api/dashboard'
import LeagueCard from '../components/dashboard/LeagueCard'
import AlertPanel from '../components/dashboard/AlertPanel'
import UpgradesTable from '../components/dashboard/UpgradesTable'
import AllRostersGrid from '../components/dashboard/AllRostersGrid'
import TopAvailablePanel from '../components/dashboard/TopAvailablePanel'
import Spinner from '../components/ui/Spinner'

export default function DashboardPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['leagues'],
    queryFn: () => dashboardApi.getLeagues(),
    staleTime: 600_000,
  })

  const leagues = data?.leagues ?? []

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⚾</span>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Fantasy Baseball Control Panel</h1>
            <p className="text-xs text-gray-500">{leagues.length > 0 ? `${leagues.length} leagues · 2026` : 'Loading...'}</p>
          </div>
        </div>
        <Link
          to="/players"
          className="btn-primary flex items-center gap-1.5 text-sm"
        >
          🔍 Player Lookup
        </Link>
      </header>

      <main className="max-w-screen-2xl mx-auto px-4 py-6 space-y-6">
        {/* League Cards */}
        <section>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Your Leagues</h2>
          {isLoading && (
            <div className="flex items-center gap-2 text-gray-500"><Spinner /> Loading leagues...</div>
          )}
          {isError && <p className="text-red-500 text-sm">Error: {String(error)}</p>}
          {!isLoading && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {leagues.map((league) => (
                <LeagueCard key={league.league_id} league={league} />
              ))}
            </div>
          )}
        </section>

        {/* Alert Panel */}
        <AlertPanel />

        {/* Two-column layout for upgrades + top available */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <UpgradesTable />
          <TopAvailablePanel />
        </div>

        {/* All Rosters */}
        <AllRostersGrid />
      </main>
    </div>
  )
}
