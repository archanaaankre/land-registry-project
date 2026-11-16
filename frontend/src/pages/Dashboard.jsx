import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listParcels } from '../services/parcelService.js'
import { listTransfers } from '../services/transferService.js'
import PageHeader from '../components/layout/PageHeader.jsx'
import { ParcelStatusChart, TransferStatusChart } from '../components/charts/index.js'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [parcels, setParcels] = useState([])
  const [transfers, setTransfers] = useState([])
  const [parcelsLoading, setParcelsLoading] = useState(true)
  const [transfersLoading, setTransfersLoading] = useState(true)
  const [parcelsError, setParcelsError] = useState('')
  const [transfersError, setTransfersError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadParcels = useCallback(async (signal) => {
    setParcelsLoading(true)
    setParcelsError('')
    try {
      const items = await listParcels({ signal })
      if (!signal.aborted) {
        setParcels(items)
        setParcelsError('')
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
        setParcels([])
        setParcelsError(
          requestError.message || 'We couldn’t load parcel statistics. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setParcelsLoading(false)
      }
    }
  }, [logout, navigate])

  const loadTransfers = useCallback(async (signal) => {
    setTransfersLoading(true)
    setTransfersError('')
    try {
      const items = await listTransfers({ signal })
      if (!signal.aborted) {
        setTransfers(items)
        setTransfersError('')
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
        setTransfers([])
        setTransfersError(
          requestError.message || 'We couldn’t load transfer statistics. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setTransfersLoading(false)
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    async function loadDashboardData() {
      await Promise.all([
        loadParcels(controller.signal),
        loadTransfers(controller.signal),
      ])
    }
    loadDashboardData()
    return () => controller.abort()
  }, [loadParcels, loadTransfers, reloadKey])

  function reloadDashboard() {
    setParcelsError('')
    setTransfersError('')
    setReloadKey((current) => current + 1)
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="registry-page dashboard-page">
      <PageHeader
        eyebrow="Authenticated workspace"
        intro="Your land registry workspace, parcel statistics, and transfer overview."
        title={`Welcome${user.name ? `, ${user.name}` : ''}`}
      />

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

      <section className="registry-panel" aria-labelledby="dashboard-charts-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="dashboard-charts-heading">Registry overview</h2>
            <p className="result-count">
              Real-time statistics from the registry API
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={reloadDashboard}
            type="button"
          >
            Refresh
          </button>
        </div>

        <div className="dashboard-charts-grid">
          <ParcelStatusChart
            parcels={parcels}
            loading={parcelsLoading}
            error={parcelsError}
          />
          <TransferStatusChart
            transfers={transfers}
            loading={transfersLoading}
            error={transfersError}
          />
        </div>

        {(parcelsError || transfersError) && (
          <button
            className="secondary-button"
            onClick={reloadDashboard}
            type="button"
          >
            Retry
          </button>
        )}
      </section>
    </main>
  )
}
