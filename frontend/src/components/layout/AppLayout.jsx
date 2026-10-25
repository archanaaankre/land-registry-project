import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/useAuth.js'
import { NAV_ITEMS } from './navItems.js'

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const navigationItems = NAV_ITEMS.filter((item) => item.roles.includes(user?.role))

  useEffect(() => {
    if (!menuOpen) {
      return undefined
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [menuOpen])

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="app-header">
        <div className="app-header-inner">
          <Link className="brand" to="/dashboard">
            <span aria-hidden="true" className="brand-mark">LR</span>
            <span>Land Registry</span>
          </Link>
          <button
            aria-controls="primary-navigation"
            aria-expanded={menuOpen}
            aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            className="app-nav-toggle"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            <span aria-hidden="true" className="app-nav-toggle-bars"><span /><span /><span /></span>
          </button>
          <nav
            aria-label="Primary navigation"
            className={`app-nav${menuOpen ? ' app-nav-open' : ''}`}
            id="primary-navigation"
          >
            <ul className="app-nav-list">
              {navigationItems.map((item) => (
                <li key={item.to}>
                  <NavLink
                    className={({ isActive }) => `app-nav-link${isActive ? ' active' : ''}`}
                    end={item.to === '/dashboard'}
                    onClick={() => setMenuOpen(false)}
                    to={item.to}
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="app-header-actions">
            <span className="app-user-role">{user?.role}</span>
            <button className="secondary-button" onClick={handleLogout} type="button">Sign out</button>
          </div>
        </div>
      </header>
      <div className="app-main" id="main-content" tabIndex="-1">
        <Outlet />
      </div>
      <footer className="app-footer">
        <div className="app-footer-inner">
          <p>Academic prototype. Not an official land registry service.</p>
        </div>
      </footer>
    </div>
  )
}
