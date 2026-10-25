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
    <main className="registry-page dashboard-page">
      <header className="registry-header">
        <div>
          <p className="eyebrow">Authenticated workspace</p>
          <h1 id="dashboard-title">Welcome{user.name ? `, ${user.name}` : ''}</h1>
          <p className="registry-intro">Your land registry workspace and account details.</p>
        </div>
      </header>
      <section className="registry-panel dashboard-card" aria-labelledby="account-heading">
        <h2 id="account-heading">Account</h2>
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
            <Link to="/parcels">Browse parcel records</Link>
            <Link to="/evaluation">Evaluation dashboard</Link>
            {user?.role === 'CITIZEN' && <Link to="/transfers">Transfer requests</Link>}
            {user?.role === 'REGISTRAR' && <Link to="/registrar/transfers">Review transfers</Link>}
          </div>
          <button className="secondary-button" onClick={handleLogout} type="button">
            Sign out
          </button>
        </nav>
      </section>
    </main>
  )
}
