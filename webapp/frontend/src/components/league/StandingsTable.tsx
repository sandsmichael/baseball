import type { Standings } from '../../types'

interface Props {
  standings: Standings[]
  myTeamName?: string
}

export default function StandingsTable({ standings, myTeamName }: Props) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-xs text-gray-500">
          <th className="text-left py-2 font-medium w-8">#</th>
          <th className="text-left py-2 font-medium">Team</th>
          <th className="text-right py-2 font-medium">W</th>
          <th className="text-right py-2 font-medium">L</th>
          <th className="text-right py-2 font-medium">T</th>
          <th className="text-right py-2 font-medium">Pct</th>
          <th className="text-right py-2 font-medium">GB</th>
        </tr>
      </thead>
      <tbody>
        {standings.map((s, i) => {
          const isMe = myTeamName && s.team.toLowerCase().includes(myTeamName.toLowerCase().substring(0, 8))
          return (
            <tr
              key={i}
              className={`table-row-hover border-b last:border-0 ${isMe ? 'bg-blue-50 font-semibold' : ''}`}
            >
              <td className="py-2 text-gray-500">{s.rank}</td>
              <td className="py-2">{s.team}</td>
              <td className="py-2 text-right">{s.wins}</td>
              <td className="py-2 text-right">{s.losses}</td>
              <td className="py-2 text-right">{s.ties}</td>
              <td className="py-2 text-right">{(s.pct * 100).toFixed(1)}</td>
              <td className="py-2 text-right text-gray-500">{s.gb}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
