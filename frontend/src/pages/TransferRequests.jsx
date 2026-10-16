import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listParcels } from '../services/parcelService.js'
import {
  createTransfer,
  listTransfers,
  transferStatusLabel,
} from '../services/transferService.js'

export default function TransferRequests() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [requests, setRequests] = useState([])
  const [parcels, setParcels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const [parcelId, setParcelId] = useState('')
  const [buyerReference, setBuyerReference] = useState('')
  const [confirmOwnership, setConfirmOwnership] = useState(false)

  const loadRequests = useCallback(async (signal) => {
    try {
      const items = await listTransfers({ signal })
      if (!signal.aborted) {
        setRequests(items)
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
        setRequests([])
        setError(requestError.message)
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return
      setLoading(true)
    })
    const tasks = Promise.allSettled([
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadRequests(controller.signal),
      listParcels({ signal: controller.signal })
        .then((items) => {
          if (!controller.signal.aborted) setParcels(items)
        })
        .catch(() => {
          if (!controller.signal.aborted) setParcels([])
        }),
    ])
    tasks.finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })

    return () => controller.abort()
  }, [loadRequests, reloadKey])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!parcelId || !buyerReference.trim() || !confirmOwnership) {
      setSubmitError('Parcel, buyer, and ownership confirmation are required.')
      return
    }

    setSubmitting(true)
    setSubmitError('')
    try {
      await createTransfer({
        parcel_id: parcelId,
        buyer_reference: buyerReference.trim(),
      })
      setParcelId('')
      setBuyerReference('')
      setConfirmOwnership(false)
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setSubmitError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="registry-page">
      <header className="registry-header">
        <div>
          <p className="eyebrow">Land Registry</p>
          <h1>Transfer requests</h1>
          <p className="registry-intro">Submit and track parcels you are authorized to transfer.</p>
        </div>
        <Link className="text-link" to="/dashboard">Back to account</Link>
      </header>

      <section className="registry-panel" aria-labelledby="new-transfer-heading">
        <h2 id="new-transfer-heading">New transfer request</h2>
        {submitError ? <p className="registry-state error-state" role="alert">{submitError}</p> : null}
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Parcel
            <select
              value={parcelId}
              onChange={(event) => setParcelId(event.target.value)}
              required
            >
              <option value="">Select a parcel</option>
              {parcels.map((parcel) => (
                <option key={parcel.parcel_id} value={parcel.parcel_id}>
                  {parcel.cadastral_number} ({parcel.parcel_id})
                </option>
              ))}
            </select>
          </label>
          <label>
            Buyer reference
            <input
              type="text"
              value={buyerReference}
              onChange={(event) => setBuyerReference(event.target.value)}
              placeholder="Registered email or user identifier"
              required
            />
          </label>
          <label className="checkbox-label">
            <input
              checked={confirmOwnership}
              onChange={(event) => setConfirmOwnership(event.target.checked)}
              type="checkbox"
            />
            I confirm that I am the current owner of the selected parcel and understand that
            registrar approval does not by itself complete a blockchain transfer.
          </label>
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? 'Submitting…' : 'Submit transfer request'}
          </button>
        </form>
      </section>

      <section className="registry-panel" aria-labelledby="transfer-list-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="transfer-list-heading">Your transfer requests</h2>
            {!loading && !error && (
              <p className="result-count">{requests.length} request{requests.length === 1 ? '' : 's'}</p>
            )}
          </div>
          <button
            className="secondary-button"
            onClick={() => setReloadKey((current) => current + 1)}
            type="button"
          >
            Refresh
          </button>
        </div>

        {loading ? <p className="registry-state" role="status">Loading transfer requests…</p> : null}
        {!loading && error ? <p className="registry-state error-state" role="alert">{error}</p> : null}
        {!loading && !error && requests.length === 0 ? (
          <p className="registry-state">No transfer requests are available.</p>
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
                  <div><dt>Buyer</dt><dd>{request.buyer_reference}</dd></div>
                  <div><dt>Status</dt><dd>{transferStatusLabel(request.status)}</dd></div>
                  <div><dt>Updated</dt><dd>{new Date(request.updated_at).toLocaleString()}</dd></div>
                </dl>
                <Link className="parcel-link" to={`/transfers/${encodeURIComponent(request.request_id)}`}>
                  View details
                </Link>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </main>
  )
}