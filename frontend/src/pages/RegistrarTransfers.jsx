import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listRegistrarTransfers, transferStatusLabel } from '../services/transferService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

export default function RegistrarTransfers() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadRequests = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const items = await listRegistrarTransfers({ signal })
      if (!signal.aborted) setRequests(items)
    } catch (requestError) {
      if (requestError.name === 'AbortError' || signal.aborted) return
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      if (!signal.aborted) {
        setRequests([])
        setError(
          requestError.message || 'We couldn’t load transfer requests for review. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) setLoading(false)
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => loadRequests(controller.signal))
    return () => controller.abort()
  }, [loadRequests, reloadKey])

  return (
    <main className="registry-page">
      <PageHeader
        actions={
          <div className="dashboard-navigation">
            <button
              className="secondary-button"
              disabled={loading}
              onClick={() => setReloadKey((current) => current + 1)}
              type="button"
            >
              {loading ? 'Refreshing…' : 'Refresh queue'}
            </button>
            <Link className="text-link" to="/transfers">All transfers</Link>
            <Link className="text-link" to="/dashboard">Back to account</Link>
          </div>
        }
        eyebrow="Registrar review"
        intro="Review, approve, or reject requests awaiting decision."
        title="Pending transfer requests"
      />

      {loading ? <p className="registry-state" role="status">Loading review queue…</p> : null}
      {!loading && error ? <p className="registry-state error-state" role="alert">{error}</p> : null}
      {!loading && !error && requests.length === 0 ? (
        <p className="registry-state">No requests are awaiting review.</p>
      ) : null}
      {!loading && !error && requests.length > 0 ? (
        <div className="ownership-list">
          {requests.map((request) => (
            <article className="ownership-record" key={request.request_id}>
              <span className={`status-badge status-${String(request.status).toLowerCase()}`}>
                {transferStatusLabel(request.status)}
              </span>
              <dl>
                <div><dt>Request</dt><dd>{request.request_id}</dd></div>
                <div><dt>Parcel</dt><dd>{request.parcel_id}</dd></div>
                <div><dt>Seller</dt><dd>{request.seller_id}</dd></div>
                <div><dt>Buyer</dt><dd>{request.buyer_reference}</dd></div>
                <div><dt>Submitted</dt><dd>{new Date(request.created_at).toLocaleString()}</dd></div>
              </dl>
              <Link className="parcel-link" to={`/transfers/${encodeURIComponent(request.request_id)}`}>
                Review request
              </Link>
            </article>
          ))}
        </div>
      ) : null}
    </main>
  )
}