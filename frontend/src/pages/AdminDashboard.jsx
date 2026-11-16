import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { getAdminStats } from '../services/adminService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

export default function AdminDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadStats = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const data = await getAdminStats({ signal })
      if (!signal.aborted) {
        setStats(data)
        setError('')
      }
    } catch (requestError) {
      if (requestError.name === 'AbortError' || signal.aborted) {
        return
      }
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      if (!signal.aborted) {
        setStats(null)
        setError(
          requestError.message || 'We couldn’t load system statistics. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false)
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    async function loadStatsData() {
      await loadStats(controller.signal)
    }
    loadStatsData()
    return () => controller.abort()
  }, [loadStats, reloadKey])

  function reloadStats() {
    setError('')
    setReloadKey((current) => current + 1)
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="registry-page">
      <PageHeader
        eyebrow="System administration"
        intro="View system statistics, user accounts, and registry overview."
        title="Admin Dashboard"
      />

      <section className="registry-panel dashboard-card" aria-labelledby="account-heading">
        <h2 id="account-heading">Admin Account</h2>
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
            <Link to="/admin/users">Manage users</Link>
            <Link to="/parcels">Browse parcel records</Link>
            <Link to="/evaluation">Evaluation dashboard</Link>
          </div>
          <button className="secondary-button" onClick={handleLogout} type="button">
            Sign out
          </button>
        </nav>
      </section>

      <section className="registry-panel" aria-labelledby="admin-stats-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="admin-stats-heading">System statistics</h2>
            <p className="result-count">Real-time statistics from the registry API</p>
          </div>
          <button
            className="secondary-button"
            onClick={reloadStats}
            type="button"
          >
            Refresh
          </button>
        </div>

        {loading && <p className="registry-state" role="status">Loading system statistics…</p>}
        {!loading && error && (
          <div className="registry-state error-state" role="alert">
            <p>{error}</p>
            <button
              className="secondary-button"
              onClick={reloadStats}
              type="button"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && stats ? (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <h3>Total Users</h3>
                <p className="stat-value">{stats.users.total}</p>
                <p className="stat-detail">
                  {stats.users.active} active, {stats.users.inactive} inactive
                </p>
              </div>
              <div className="stat-card">
                <h3>Total Parcels</h3>
                <p className="stat-value">{stats.parcels.total}</p>
              </div>
              <div className="stat-card">
                <h3>Total Transfers</h3>
                <p className="stat-value">{stats.transfers.total}</p>
              </div>
            </div>

            <div className="role-breakdown">
              <h3>Users by Role</h3>
              <div className="role-list">
                {Object.entries(stats.users.by_role).map(([role, count]) => (
                  <div key={role} className="role-item">
                    <span className="role-label">{role}</span>
                    <span className="role-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}
      </section>
    </main>
  )
}
