import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listRegistrarTransfers } from '../services/transferService.js'
import { transferStatusLabel } from '../services/transferService.js'

export default function RegistrarTransfers() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // refresh is handled by a new page load

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
        setError(requestError.message)
      }
    } finally {
      if (!signal.aborted) setLoading(false)
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => loadRequests(controller.signal))
    return () => controller.abort()
  }, [loadRequests])

  return (
    <main className="registry-page">
      <header className="registry-header">
        <div>
          <p className="eyebrow">Registrar review</p>
          <h1>Pending transfer requests</h1>
          <p className="registry-intro">Review, approve, or reject requests awaiting decision.</p>
        </div>
        <div className="dashboard-navigation">
          <Link className="text-link" to="/transfers">All transfers</Link>
          <Link className="text-link" to="/dashboard">Back to account</Link>
        </div>
      </header>

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