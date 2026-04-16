import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Browse from './pages/Browse'
import History from './pages/History'
import Cart from './pages/Cart'
import Settings from './pages/Settings'
import Log from './pages/Log'
import Admin from './pages/Admin'

const Spinner = () => (
  <div className="min-h-screen flex items-center justify-center bg-gray-950">
    <div className="w-8 h-8 rounded-full border-2 border-bw-blue border-t-transparent animate-spin" />
  </div>
)

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  return user ? children : <Navigate to="/login" replace />
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  return user.is_admin ? children : <Navigate to="/" replace />
}

function AppRoutes() {
  const { user, loading } = useAuth()

  if (loading) return <Spinner />

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
              <Navbar />
              <main className="flex-1 overflow-hidden">
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/browse" element={<Browse />} />
                  <Route path="/history" element={<History />} />
                  <Route path="/cart" element={<Cart />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/log" element={<Log />} />
                  <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </main>
            </div>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
