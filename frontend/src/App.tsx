import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import TicketDetail from './pages/TicketDetail'
import Screen from './pages/Screen'
import Monitor from './pages/Monitor'
import MyTickets from './pages/MyTickets'
import ProcessOverview from './pages/ProcessOverview'
import Evaluations from './pages/Evaluations'
import AppShell from './components/AppShell'
import { getSessionUser } from './types/auth'

function RequireSession() {
  return getSessionUser() ? <Outlet /> : <Navigate to="/login" replace />
}

function RoleHome() {
  const user = getSessionUser()
  return <Navigate to={user?.role === 'sv' ? '/monitor' : '/my-tickets'} replace />
}

function SupervisorOnly({ children }: { children: React.ReactElement }) {
  return getSessionUser()?.role === 'sv' ? children : <Navigate to="/my-tickets" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireSession />}>
          <Route element={<AppShell />}>
            <Route path="/" element={<RoleHome />} />
            <Route path="/workspace" element={<Dashboard showScreen />} />
            <Route path="/my-tickets" element={<MyTickets />} />
            <Route path="/monitor" element={<SupervisorOnly><Monitor /></SupervisorOnly>} />
            <Route path="/approvals" element={<SupervisorOnly><Monitor /></SupervisorOnly>} />
            <Route path="/process" element={<ProcessOverview />} />
            <Route path="/ticket/:id" element={<TicketDetail />} />
            <Route path="/screen" element={<SupervisorOnly><Screen /></SupervisorOnly>} />
            <Route path="/evaluations" element={<SupervisorOnly><Evaluations /></SupervisorOnly>} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
