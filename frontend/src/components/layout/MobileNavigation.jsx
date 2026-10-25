import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../context/useAuth.js'
import { NAV_ITEMS } from './navItems.js'

export default function MobileNavigation({ items = NAV_ITEMS }) {
  const [open, setOpen] = useState(false)
  const { user } = useAuth()

  useEffect(() => {
    if (!open) {
      return undefined
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const toggleOpen = () => setOpen((value) => !value)
  const visibleItems = items.filter((item) => item.roles.includes(user?.role))

  return (
    <>
      <button
        className="mobile-nav-toggle"
        type="button"
        aria-expanded={open}
        aria-controls="mobile-navigation-panel"
        aria-label={open ? 'Close menu' : 'Open menu'}
        onClick={toggleOpen}
      >
        <svg aria-hidden="true" height="22" viewBox="0 0 24 24" width="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 6h16" />
          <path d="M4 12h16" />
          <path d="M4 18h16" />
        </svg>
      </button>
      {open ? (
        <div className="mobile-nav-panel" id="mobile-navigation-panel">
          <nav className="app-sidebar-nav" aria-label="Mobile navigation">
            {visibleItems.map((item) => (
              <NavLink
                className={({ isActive }) => `app-sidebar-link${isActive ? ' active' : ''}`}
                key={item.to}
                onClick={() => setOpen(false)}
                to={item.to}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <button className="secondary-button" onClick={() => setOpen(false)} type="button">
            Close
          </button>
        </div>
      ) : null}
    </>
  )
}
