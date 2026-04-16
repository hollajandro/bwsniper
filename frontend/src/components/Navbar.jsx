import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const NAV_ITEMS = [
  { path: '/',         label: 'Dashboard' },
  { path: '/browse',   label: 'Browse' },
  { path: '/history',  label: 'History' },
  { path: '/cart',     label: 'Cart' },
  { path: '/log',      label: 'Log' },
  { path: '/settings', label: 'Settings' },
]

export default function Navbar() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  const navItems = user?.is_admin
    ? [...NAV_ITEMS, { path: '/admin', label: 'Admin' }]
    : NAV_ITEMS

  return (
    <>
      <nav className="bg-gray-900 border-b border-gray-800 px-5 flex items-center justify-between h-[52px] shadow-mat-1 z-40 shrink-0">
        {/* Logo + nav */}
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <span className="w-7 h-7 rounded-lg bg-bw-blue flex items-center justify-center text-white text-xs font-bold shadow-mat-1">
              BW
            </span>
            <span className="font-semibold text-white text-sm tracking-tight hidden sm:block">
              Sniper
            </span>
          </Link>

          <div className="hidden md:flex items-center">
            {navItems.map(({ path, label }) => {
              const active = location.pathname === path
              return (
                <Link
                  key={path}
                  to={path}
                  className={`relative px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    active
                      ? 'text-white'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
                  }`}
                >
                  {label}
                  {active && (
                    <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-bw-blue" />
                  )}
                </Link>
              )
            })}
          </div>
        </div>

        {/* User */}
        <div className="hidden md:flex items-center gap-2.5">
          <span className="text-xs text-gray-400 hidden md:block">
            {user?.display_name || user?.email}
          </span>
          <button
            onClick={logout}
            className="px-2.5 py-1.5 text-xs rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 border border-gray-700/70 transition-colors"
          >
            Logout
          </button>
        </div>

        <button
          className="md:hidden p-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          onClick={() => setMenuOpen(m => !m)}
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
        >
          {menuOpen ? '✕' : '☰'}
        </button>
      </nav>
      {menuOpen && (
        <div className="md:hidden bg-gray-900 border-b border-gray-800 px-4 py-2 space-y-0.5 z-30">
          {navItems.map(({ path, label }) => {
            const active = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                onClick={() => setMenuOpen(false)}
                className={`block px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800/60'
                }`}
              >
                {label}
              </Link>
            )
          })}
          <div className="pt-2 border-t border-gray-800 flex items-center justify-between px-3 pb-1">
            <span className="text-xs text-gray-400">{user?.display_name || user?.email}</span>
            <button onClick={logout} className="text-xs text-gray-400 hover:text-white transition-colors">
              Logout
            </button>
          </div>
        </div>
      )}
    </>
  )
}
