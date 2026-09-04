import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import TicketDetail from './pages/TicketDetail'
import Screen from './pages/Screen'
import Monitor from './pages/Monitor'
import MyTickets from './pages/MyTickets'
import ProcessOverview from './pages/ProcessOverview'
import Evaluations from './pages/Evaluations'
import SecurityGovernance from './pages/SecurityGovernance'
import BackofficeShell from './components/BackofficeShell'
import CustomerShell from './components/CustomerShell'
import { getSessionUser } from './types/auth'
import ShopHome from './pages/ShopHome'
import ProductDetail from './pages/ProductDetail'
import Cart from './pages/Cart'
import Checkout from './pages/Checkout'
import Orders from './pages/Orders'
import OrderDetail from './pages/OrderDetail'
import Returns from './pages/Returns'
import ServiceRefunds from './pages/ServiceRefunds'

function RequireSession() {
  return getSessionUser() ? <Outlet /> : <Navigate to="/login" replace />
}

function RoleHome() {
  const user = getSessionUser()
  return <Navigate to={user?.role === 'customer' ? '/shop' : user?.role === 'cs' ? '/service/refunds' : '/monitor'} replace />
}

function CustomerOnly({ children }: { children: React.ReactElement }) {
  return getSessionUser()?.role === 'customer' ? children : <RoleHome />
}

function SupervisorOnly({ children }: { children: React.ReactElement }) {
  return getSessionUser()?.role === 'sv' ? children : <Navigate to="/service/refunds" replace />
}

function StaffOnly({ children }: { children: React.ReactElement }) {
  return getSessionUser()?.role === 'customer' ? <Navigate to="/shop" replace /> : children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireSession />}>
          <Route element={<CustomerOnly><CustomerShell /></CustomerOnly>}>
            <Route path="/shop" element={<ShopHome />} />
            <Route path="/shop/products/:id" element={<ProductDetail />} />
            <Route path="/shop/cart" element={<Cart />} />
            <Route path="/shop/checkout" element={<Checkout />} />
            <Route path="/shop/orders" element={<Orders />} />
            <Route path="/shop/orders/:id" element={<OrderDetail />} />
            <Route path="/shop/returns" element={<Returns />} />
          </Route>
          <Route element={<StaffOnly><BackofficeShell /></StaffOnly>}>
            <Route path="/" element={<RoleHome />} />
            <Route path="/workspace" element={<SupervisorOnly><Dashboard showScreen /></SupervisorOnly>} />
            <Route path="/my-tickets" element={<SupervisorOnly><MyTickets /></SupervisorOnly>} />
            <Route path="/monitor" element={<SupervisorOnly><Monitor /></SupervisorOnly>} />
            <Route path="/approvals" element={<SupervisorOnly><Monitor /></SupervisorOnly>} />
            <Route path="/process" element={<SupervisorOnly><ProcessOverview /></SupervisorOnly>} />
            <Route path="/ticket/:id" element={<SupervisorOnly><TicketDetail /></SupervisorOnly>} />
            <Route path="/screen" element={<SupervisorOnly><Screen /></SupervisorOnly>} />
            <Route path="/evaluations" element={<SupervisorOnly><Evaluations /></SupervisorOnly>} />
            <Route path="/security-governance" element={<SupervisorOnly><SecurityGovernance /></SupervisorOnly>} />
            <Route path="/service/refunds" element={<ServiceRefunds />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
