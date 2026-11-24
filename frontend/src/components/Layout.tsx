import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const links: Array<{ to: string; label: string; staffOnly?: boolean }> = [
  { to: '/', label: 'Dashboard' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/reviews', label: 'Review queue', staffOnly: true },
  { to: '/customers', label: 'Customers' },
  { to: '/audit', label: 'Audit', staffOnly: true },
  { to: '/model', label: 'Model', staffOnly: true },
  { to: '/visualizations', label: 'Visualizations', staffOnly: true },
  { to: '/monitoring', label: 'Monitoring', staffOnly: true },
]

export function Layout() {
  const { user, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const staff = hasRole('ADMIN', 'ANALYST')

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">RiskPulse</div>
        <nav aria-label="Main">
          {links.filter((l) => !l.staffOnly || staff).map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === '/'}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <div>{user?.username}</div>
          <div className="muted small">{user?.role}</div>
          <button
            className="link"
            onClick={async () => {
              await logout()
              navigate('/login')
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
