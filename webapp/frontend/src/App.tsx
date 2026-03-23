import { BrowserRouter, Routes, Route } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import LeaguePage from './pages/LeaguePage'
import PlayersPage from './pages/PlayersPage'
import ToastContainer from './components/ui/ToastContainer'

export default function App() {
  return (
    <BrowserRouter>
      <ToastContainer />
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/players" element={<PlayersPage />} />
        <Route path="/league/:leagueId" element={<LeaguePage />} />
      </Routes>
    </BrowserRouter>
  )
}
