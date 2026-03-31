import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../api/dashboard'
import LeagueCard from '../components/dashboard/LeagueCard'
import AlertPanel from '../components/dashboard/AlertPanel'
import UpgradesTable from '../components/dashboard/UpgradesTable'
import PlayerMatrixPanel from '../components/dashboard/PlayerMatrixPanel'
import TopAvailablePanel from '../components/dashboard/TopAvailablePanel'
import NavBar from '../components/ui/NavBar'
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
      <NavBar />

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

        {/* Player Exposure Matrix */}
        <PlayerMatrixPanel />
      </main>
    </div>
  )
}
