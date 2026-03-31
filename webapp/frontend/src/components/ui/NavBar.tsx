import { Link, useLocation } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/',          label: 'Dashboard'     },
  { to: '/matchups',  label: 'Matchups'      },
  { to: '/players',   label: 'Player Lookup' },
]

export default function NavBar() {
  const { pathname } = useLocation()

  return (
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
      </nav>
    </header>
  )
}
