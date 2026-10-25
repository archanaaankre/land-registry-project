import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/useAuth.js'
import { NAV_ITEMS } from './navItems.js'

export default function Sidebar({ items = NAV_ITEMS }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleSignOut() {
    logout()
    navigate('/login', { replace: true })
  }

  const visibleItems = items.filter((item) => item.roles.includes(user?.role))

  return (
    <aside className="app-sidebar">
      <Link className="app-sidebar-brand" to="/dashboard">
        Land Registry
      </Link>
      <nav className="app-sidebar-nav" aria-label="Primary navigation">
        {visibleItems.map((item) => (
          <NavLink
            className={({ isActive }) =>
              `app-sidebar-link${isActive ? ' active' : ''}`
            }
            key={item.to}
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="app-sidebar-footer">
        <dl className="app-sidebar-user">
          <div>
            <dt>Account</dt>
            <dd>{user?.name || user?.email || user?.id}</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{user?.role}</dd>
          </div>
        </dl>
        <button className="secondary-button app-sidebar-signout" onClick={handleSignOut} type="button">
          Sign out
        </button>
      </div>
    </aside>
  )
}
