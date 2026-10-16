import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import {
  approveTransfer,
  cancelTransfer,
  getTransfer,
  rejectTransfer,
  transferStatusLabel,
} from '../services/transferService.js'

const CANCELLABLE_STATUSES = new Set(['SUBMITTED', 'UNDER_REVIEW', 'DRAFT'])

export default function TransferRequestDetails() {
  const { requestId } = useParams()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [details, setDetails] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [processing, setProcessing] = useState(false)
  const [showRejectReason, setShowRejectReason] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadDetails = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const nextDetails = await getTransfer(requestId, { signal })
      if (!signal.aborted) setDetails(nextDetails)
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
        setDetails(null)
        setError(requestError.message)
      }
    } finally {
      if (!signal.aborted) setLoading(false)
    }
  }, [logout, navigate, requestId])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => loadDetails(controller.signal))
    return () => controller.abort()
  }, [loadDetails, reloadKey])

  async function handleCancel() {
    if (!window.confirm('Cancel this transfer request?')) return
    setProcessing(true)
    setActionError('')
    try {
      await cancelTransfer(requestId, 'Cancelled by requester')
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setActionError(requestError.message)
    } finally {
      setProcessing(false)
    }
  }

  async function handleApprove() {
    if (!window.confirm('Approve this transfer request? Approval alone does not complete a blockchain transfer.')) return
    setProcessing(true)
    setActionError('')
    try {
      await approveTransfer(requestId)
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setActionError(requestError.message)
    } finally {
      setProcessing(false)
    }
  }

  async function handleReject(event) {
    event.preventDefault()
    if (!rejectReason.trim()) {
      setActionError('A rejection reason is required.')
      return
    }
    setProcessing(true)
    setActionError('')
    try {
      await rejectTransfer(requestId, rejectReason.trim())
      setShowRejectReason(false)
      setRejectReason('')
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setActionError(requestError.message)
    } finally {
      setProcessing(false)
    }
  }

  const transfer = details?.transfer
  const history = details?.history ?? []
  const canCancel =
    transfer && user?.id === transfer.seller_id && CANCELLABLE_STATUSES.has(transfer.status)
  const canReview = user?.role === 'REGISTRAR' && transfer?.status === 'UNDER_REVIEW'

  if (loading) {
    return (
      <main className="registry-page">
        <p className="registry-state" role="status">Loading transfer request…</p>
      </main>
    )
  }

  if (error || !transfer) {
    return (
      <main className="registry-page">
        <header className="registry-header">
          <h1>Transfer request</h1>
          <Link className="text-link" to="/transfers">Back to transfers</Link>
        </header>
        <p className="registry-state error-state" role="alert">{error || 'Transfer request is unavailable.'}</p>
      </main>
    )
  }

  return (
    <main className="registry-page">
      <header className="registry-header">
        <div>
          <p className="eyebrow">Land Registry</p>
          <h1>Transfer request {transfer.request_id}</h1>
          <p className="registry-intro">Status: {transferStatusLabel(transfer.status)}</p>
        </div>
        <Link className="text-link" to="/transfers">Back to transfers</Link>
      </header>

      {actionError ? <p className="registry-state error-state" role="alert">{actionError}</p> : null}

      <section className="registry-panel" aria-labelledby="transfer-details-heading">
        <h2 id="transfer-details-heading">Request details</h2>
        <dl className="details-grid">
          <div><dt>Request ID</dt><dd>{transfer.request_id}</dd></div>
          <div><dt>Parcel</dt><dd>{transfer.parcel_id}</dd></div>
          <div><dt>Seller</dt><dd>{transfer.seller_id}</dd></div>
          <div><dt>Buyer</dt><dd>{transfer.buyer_reference}</dd></div>
          <div><dt>Status</dt><dd>{transferStatusLabel(transfer.status)}</dd></div>
          <div><dt>Blockchain transaction ID</dt><dd>{transfer.blockchain_tx_id || 'Not available'}</dd></div>
          <div><dt>Blockchain status</dt><dd>{transfer.blockchain_status || 'Not available'}</dd></div>
          <div><dt>Failure reason</dt><dd>{transfer.failure_reason || 'None'}</dd></div>
          <div><dt>Review reason</dt><dd>{transfer.review_reason || 'None'}</dd></div>
          <div><dt>Created</dt><dd>{new Date(transfer.created_at).toLocaleString()}</dd></div>
          <div><dt>Updated</dt><dd>{new Date(transfer.updated_at).toLocaleString()}</dd></div>
        </dl>

        {canCancel ? (
          <button className="secondary-button" disabled={processing} onClick={handleCancel} type="button">
            {processing ? 'Processing…' : 'Cancel request'}
          </button>
        ) : null}

        {canReview ? (
          <div className="measurement-toolbar">
            <button className="primary-button" disabled={processing} onClick={handleApprove} type="button">
              {processing ? 'Processing…' : 'Approve'}
            </button>
            <button
              className="secondary-button"
              disabled={processing}
              onClick={() => setShowRejectReason((value) => !value)}
              type="button"
            >
              Reject
            </button>
          </div>
        ) : null}

        {canReview && showRejectReason ? (
          <form className="auth-form" onSubmit={handleReject}>
            <label>
              Rejection reason
              <textarea
                required
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                rows={4}
              />
            </label>
            <button className="primary-button" disabled={processing} type="submit">
              {processing ? 'Processing…' : 'Confirm rejection'}
            </button>
          </form>
        ) : null}
      </section>

      <section className="registry-panel" aria-labelledby="transfer-history-heading">
        <h2 id="transfer-history-heading">Status history</h2>
        {history.length === 0 ? (
          <p className="registry-state">No status history is available.</p>
        ) : (
          <ol className="ownership-timeline">
            {history.map((event) => (
              <li className="ownership-timeline-item" key={event.event_id}>
                <article>
                  <div className="timeline-heading">
                    <strong>{event.event_type}</strong>
                    <span className="timeline-timestamp">
                      {new Date(event.created_at).toLocaleString()}
                    </span>
                  </div>
                  <dl className="timeline-details">
                    <div><dt>From</dt><dd>{event.from_status || 'Start'}</dd></div>
                    <div><dt>To</dt><dd>{event.to_status}</dd></div>
                    <div><dt>Actor</dt><dd>{event.actor_id} ({event.actor_role})</dd></div>
                    <div><dt>Reason</dt><dd>{event.reason || 'None'}</dd></div>
                  </dl>
                </article>
              </li>
            ))}
          </ol>
        )}
      </section>
    </main>
  )
}