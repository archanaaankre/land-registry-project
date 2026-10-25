import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import {
  approveTransfer,
  blockchainStatusLabel,
  cancelTransfer,
  getTransfer,
  rejectTransfer,
  transferStatusLabel,
} from '../services/transferService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

const CANCELLABLE_STATUSES = new Set(['SUBMITTED', 'UNDER_REVIEW', 'DRAFT'])

function describeTransferStatus(transfer) {
  switch (transfer.status) {
    case 'SUBMITTED':
      return 'The API reports that this request was submitted and is awaiting registrar review.'
    case 'UNDER_REVIEW':
      return 'The API reports that registrar review is in progress.'
    case 'APPROVED':
      return transfer.blockchain_status === 'UNAVAILABLE'
        ? 'The API reports registrar approval and unavailable blockchain submission. Approval alone does not transfer ownership.'
        : 'The API reports registrar approval. Approval alone does not transfer ownership; blockchain status is shown separately.'
    case 'BLOCKCHAIN_PENDING':
      return 'The API reports blockchain processing as pending. This is not confirmation of an ownership transfer.'
    case 'COMPLETED':
      return 'The API reports this request as completed. The displayed ownership records remain the source for recorded ownership.'
    default:
      return `The current status, ${transferStatusLabel(transfer.status)}, is reported by the API.`
  }
}

function formatTimestamp(value) {
  if (!value) {
    return 'Not available'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not available' : date.toLocaleString()
}

export default function TransferRequestDetails() {
  const { requestId } = useParams()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [details, setDetails] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionNotice, setActionNotice] = useState('')
  const [processing, setProcessing] = useState(false)
  const [showRejectReason, setShowRejectReason] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadedForRequestId, setLoadedForRequestId] = useState('')
  const backPath = user?.role === 'REGISTRAR' ? '/registrar/transfers' : '/transfers'

  const loadDetails = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const nextDetails = await getTransfer(requestId, { signal })
      if (!signal.aborted) {
        setDetails(nextDetails)
        setLoadedForRequestId(requestId)
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
        setDetails(null)
        setError(requestError.message || 'We couldn’t load this transfer request. Please try again.')
        setLoadedForRequestId(requestId)
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
    setActionNotice('')
    try {
      const result = await cancelTransfer(requestId, 'Cancelled by requester')
      setActionNotice(
        `The API accepted the cancellation request and returned status ${transferStatusLabel(result.status)}.`,
      )
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setActionError(
        requestError.message || 'The transfer request could not be cancelled. Please try again.',
      )
    } finally {
      setProcessing(false)
    }
  }

  async function handleApprove() {
    if (!window.confirm('Approve this transfer request? Approval alone does not complete a blockchain transfer.')) return
    setProcessing(true)
    setActionError('')
    setActionNotice('')
    try {
      const result = await approveTransfer(requestId)
      setActionNotice(
        `The API accepted the review action and returned status ${transferStatusLabel(result.status)}.`,
      )
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setActionError(
        requestError.message || 'The transfer request could not be approved. Please try again.',
      )
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
    setActionNotice('')
    try {
      const result = await rejectTransfer(requestId, rejectReason.trim())
      setActionNotice(
        `The API accepted the review action and returned status ${transferStatusLabel(result.status)}.`,
      )
      setShowRejectReason(false)
      setRejectReason('')
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setActionError(
        requestError.message || 'The transfer request could not be rejected. Please try again.',
      )
    } finally {
      setProcessing(false)
    }
  }

  const transfer = details?.transfer
  const history = details?.history ?? []
  const canCancel =
    transfer && user?.id === transfer.seller_id && CANCELLABLE_STATUSES.has(transfer.status)
  const canReview =
    user?.role === 'REGISTRAR' &&
    ['SUBMITTED', 'UNDER_REVIEW'].includes(transfer?.status)
  const isLoading = loading || loadedForRequestId !== requestId

  if (isLoading) {
    return (
      <main className="registry-page">
        {actionNotice ? <p className="registry-state" role="status">{actionNotice}</p> : null}
        <p className="registry-state" role="status">Loading transfer request…</p>
      </main>
    )
  }

  if (error || !transfer) {
    return (
      <main className="registry-page">
        <header className="registry-header">
          <h1>Transfer request</h1>
          <Link className="text-link" to={backPath}>
            {user?.role === 'REGISTRAR' ? 'Back to review queue' : 'Back to transfers'}
          </Link>
        </header>
        {actionNotice ? <p className="registry-state" role="status">{actionNotice}</p> : null}
        <p className="registry-state error-state" role="alert">{error || 'Transfer request is unavailable.'}</p>
        <button
          className="secondary-button"
          onClick={() => {
            setLoading(true)
            setError('')
            setDetails(null)
            setLoadedForRequestId('')
            setReloadKey((current) => current + 1)
          }}
          type="button"
        >
          Retry
        </button>
      </main>
    )
  }

  return (
    <main className="registry-page">
      <PageHeader
        actions={
          <Link className="text-link" to={backPath}>
            {user?.role === 'REGISTRAR' ? 'Back to review queue' : 'Back to transfers'}
          </Link>
        }
        eyebrow="Land Registry"
        intro={`Status: ${transferStatusLabel(transfer.status)}`}
        title={`Transfer request ${transfer.request_id}`}
      />

      {actionError ? <p className="registry-state error-state" role="alert">{actionError}</p> : null}
      {actionNotice ? <p className="registry-state" role="status">{actionNotice}</p> : null}
      <p className="registry-state" role="status">{describeTransferStatus(transfer)}</p>

      <section className="registry-panel" aria-labelledby="transfer-details-heading">
        <h2 id="transfer-details-heading">Request details</h2>
        <dl className="details-grid">
          <div><dt>Request ID</dt><dd>{transfer.request_id}</dd></div>
          <div><dt>Parcel</dt><dd>{transfer.parcel_id}</dd></div>
          <div><dt>Seller</dt><dd>{transfer.seller_id}</dd></div>
          <div><dt>Buyer</dt><dd>{transfer.buyer_reference}</dd></div>
          <div><dt>Status</dt><dd>{transferStatusLabel(transfer.status)}</dd></div>
          <div><dt>Blockchain transaction ID</dt><dd>{transfer.blockchain_tx_id || 'Not available'}</dd></div>
          <div><dt>Blockchain status</dt><dd>{blockchainStatusLabel(transfer.blockchain_status)}</dd></div>
          <div><dt>Failure reason</dt><dd>{transfer.failure_reason || 'Not available'}</dd></div>
          <div><dt>Review reason</dt><dd>{transfer.review_reason || 'Not provided'}</dd></div>
          <div><dt>Created</dt><dd>{formatTimestamp(transfer.created_at)}</dd></div>
          <div><dt>Updated</dt><dd>{formatTimestamp(transfer.updated_at)}</dd></div>
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
                    <span className="timeline-timestamp">{formatTimestamp(event.created_at)}</span>
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