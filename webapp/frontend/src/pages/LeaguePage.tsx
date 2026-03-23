import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { leagueApi } from '../api/league'
import type { PendingTransaction } from '../api/league'
import { dashboardApi } from '../api/dashboard'
import MatchupPanel from '../components/league/MatchupPanel'
import StandingsTable from '../components/league/StandingsTable'
import WaiverBrowser from '../components/league/WaiverBrowser'
import LineupManager from '../components/league/LineupManager'
import CacheAge from '../components/ui/CacheAge'
import Spinner from '../components/ui/Spinner'

type Tab = 'lineup' | 'matchup' | 'standings' | 'waivers'
const TABS: { id: Tab; label: string }[] = [
  { id: 'lineup', label: 'Lineup' },
  { id: 'matchup', label: 'Matchup' },
  { id: 'standings', label: 'Standings' },
  { id: 'waivers', label: 'Waivers' },
]

function TransactionsPanel({ leagueId }: { leagueId: string }) {
  const txnQ = useQuery({
    queryKey: ['transactions', leagueId],
    queryFn: () => leagueApi.getTransactions(leagueId),
    staleTime: 60_000,
  })

  if (txnQ.isLoading) return null
  if (txnQ.isError || !txnQ.data) return null

  const txns = txnQ.data.transactions
  if (!txns.length) return null

  return (
    <div className="card p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-sm">Pending Transactions</h2>
        <CacheAge age={txnQ.data.cached_age} onRefresh={() => txnQ.refetch()} />
      </div>
      <div className="space-y-2">
        {txns.map((t: PendingTransaction, i: number) => (
          <div key={i} className="flex items-start gap-3 text-sm border rounded-lg px-3 py-2 bg-amber-50 border-amber-200">
            <span className={`mt-0.5 text-xs font-semibold px-1.5 py-0.5 rounded uppercase ${
              t.type === 'pending_trade' ? 'bg-purple-100 text-purple-700' : 'bg-amber-100 text-amber-700'
            }`}>
              {t.type === 'pending_trade' ? 'Trade' : 'Waiver'}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {t.adds.map((p, j) => (
                  <span key={j} className="text-green-700">
                    + {p.name} <span className="text-gray-400">({p.team} {p.positions})</span>
                  </span>
                ))}
                {t.drops.map((p, j) => (
                  <span key={j} className="text-red-600">
                    − {p.name} <span className="text-gray-400">({p.team} {p.positions})</span>
                  </span>
                ))}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {t.date && <span>{t.date}</span>}
                {t.waiver_priority != null && <span className="ml-2">Priority #{t.waiver_priority}</span>}
                {t.faab_bid != null && <span className="ml-2">FAAB ${t.faab_bid}</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function LeaguePage() {
  const { leagueId } = useParams<{ leagueId: string }>()
  const [tab, setTab] = useState<Tab>('lineup')

  const leagues = useQuery({
    queryKey: ['leagues'],
    queryFn: () => dashboardApi.getLeagues(),
    staleTime: 600_000,
  })
  const league = leagues.data?.leagues.find((l) => l.league_id === leagueId)

  const roster = useQuery({
    queryKey: ['roster', leagueId],
    queryFn: () => leagueApi.getRoster(leagueId!),
    staleTime: 60_000,
    enabled: !!leagueId,
  })

  const matchup = useQuery({
    queryKey: ['matchup', leagueId],
    queryFn: () => leagueApi.getMatchup(leagueId!),
    staleTime: 300_000,
    enabled: !!leagueId && tab === 'matchup',
  })

  const oppRoster = useQuery({
    queryKey: ['opp-roster', leagueId],
    queryFn: () => leagueApi.getOpponentRoster(leagueId!),
    staleTime: 300_000,
    enabled: !!leagueId && tab === 'matchup',
  })

  const standings = useQuery({
    queryKey: ['standings', leagueId],
    queryFn: () => leagueApi.getStandings(leagueId!),
    staleTime: 300_000,
    enabled: !!leagueId && tab === 'standings',
  })

  const players = roster.data?.roster ?? []

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-3 mb-1">
          <Link to="/" className="text-blue-600 hover:text-blue-700 text-sm">← Dashboard</Link>
        </div>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {league?.team_name ?? leagueId}
            </h1>
            <p className="text-sm text-gray-500">{league?.name}</p>
          </div>
          {league && (
            <div className="text-xs text-gray-400 text-right">
              <div>{league.scoring_method} · {league.num_teams} teams</div>
              <div>League ID: {leagueId}</div>
            </div>
          )}
        </div>
      </header>

      {/* Tab Bar */}
      <div className="bg-white border-b border-gray-200 px-6">
        <nav className="flex gap-0">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-6">

        {/* Matchup Tab */}
        {tab === 'matchup' && (
          <div>
            {matchup.isLoading || oppRoster.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-500 py-4"><Spinner size="sm" /> Loading matchup...</div>
            ) : (
              <MatchupPanel
                leagueId={leagueId!}
                matchup={matchup.data?.matchup ?? null}
                oppRoster={oppRoster.data?.roster ?? []}
              />
            )}
          </div>
        )}

        {/* Standings Tab */}
        {tab === 'standings' && (
          <div className="card p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">Standings</h2>
              <CacheAge
                age={standings.data?.cached_age}
                onRefresh={() => standings.refetch()}
              />
            </div>
            {standings.isLoading && (
              <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
            )}
            {!standings.isLoading && standings.data && (
              <StandingsTable
                standings={standings.data.standings}
                myTeamName={league?.team_name}
              />
            )}
          </div>
        )}

        {/* Waivers Tab */}
        {tab === 'waivers' && (
          <div className="card p-4">
            <h2 className="font-semibold mb-4">Waiver Wire & Free Agents</h2>
            <WaiverBrowser leagueId={leagueId!} roster={players} />
          </div>
        )}

        {/* Lineup Tab */}
        {tab === 'lineup' && (
          <div>
            <TransactionsPanel leagueId={leagueId!} />
            <div className="card p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold">Lineup Management</h2>
                <CacheAge
                  age={roster.data?.cached_age}
                  onRefresh={() => roster.refetch()}
                />
              </div>
              {roster.isLoading && (
                <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner size="sm" /> Loading...</div>
              )}
              {!roster.isLoading && players.length > 0 && (
                <LineupManager leagueId={leagueId!} players={players} />
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
