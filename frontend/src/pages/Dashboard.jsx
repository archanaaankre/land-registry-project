import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="auth-page">
      <section className="auth-card dashboard-card" aria-labelledby="dashboard-title">
        <p className="eyebrow">Authenticated workspace</p>
        <h1 id="dashboard-title">Land Registry System</h1>
        <p className="auth-intro">You are signed in with your verified account role.</p>
        <dl className="identity-details">
          <div>
            <dt>Account</dt>
            <dd>{user.name || user.email || user.id}</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{user.role}</dd>
          </div>
        </dl>
        <nav className="dashboard-links" aria-label="Account navigation">
          <div className="dashboard-navigation">
            <Link to="/parcels">Browse parcels</Link>
            <Link to="/health">Backend status</Link>
          </div>
          <button className="secondary-button" onClick={handleLogout} type="button">
            Sign out
          </button>
        </nav>
      </section>
    </main>
  )
}
