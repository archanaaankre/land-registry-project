import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listParcels } from '../services/parcelService.js'
import {
  createTransfer,
  listTransfers,
  transferStatusLabel,
} from '../services/transferService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

export default function TransferRequests() {
  const { user, logout } = useAuth()
  const isCitizen = user?.role === 'CITIZEN'
  const location = useLocation()
  const navigate = useNavigate()
  const [requests, setRequests] = useState([])
  const [parcels, setParcels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [parcelLoadError, setParcelLoadError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submittedTransfer, setSubmittedTransfer] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const [parcelId, setParcelId] = useState(() => location.state?.parcelId ?? '')
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
        setError('We couldn’t load transfer requests. Please try again.')
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return
      setLoading(true)
    })
    const requestTask = Promise.resolve().then(() => {
      if (controller.signal.aborted) return
      return loadRequests(controller.signal)
    })
    const parcelTask = isCitizen
      ? Promise.resolve().then(() => {
        if (controller.signal.aborted) return
        return listParcels({ signal: controller.signal })
          .then((items) => {
            if (!controller.signal.aborted) {
              setParcels(items)
              setParcelLoadError('')
            }
          })
          .catch((requestError) => {
            if (requestError.name === 'AbortError' || controller.signal.aborted) {
              return
            }
            if (requestError.status === 401) {
              logout()
              navigate('/login', { replace: true })
              return
            }
            if (!controller.signal.aborted) {
              setParcels([])
              setParcelLoadError('We couldn’t load available land records for a new request. Please try again.')
            }
          })
      })
      : Promise.resolve()
    const tasks = Promise.allSettled([requestTask, parcelTask])
    tasks.finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })

    return () => controller.abort()
  }, [isCitizen, loadRequests, logout, navigate, reloadKey])

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting) return
    if (user?.role !== 'CITIZEN') {
      setSubmitError('Only citizen accounts can submit transfer requests.')
      return
    }
    if (!parcelId || !buyerReference.trim() || !confirmOwnership) {
      setSubmitError('Parcel, buyer, and ownership confirmation are required.')
      setSubmittedTransfer(null)
      return
    }

    setSubmitting(true)
    setSubmitError('')
    setSubmittedTransfer(null)
    try {
      const transfer = await createTransfer({
        parcel_id: parcelId,
        buyer_reference: buyerReference.trim(),
      })
      setSubmittedTransfer(transfer)
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
      setSubmitError(
        requestError.message || 'Your transfer request could not be submitted. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="registry-page">
      <PageHeader
        actions={<Link className="text-link" to="/dashboard">Back to account</Link>}
        eyebrow="Land Registry"
        intro={user?.role === 'CITIZEN'
          ? 'Submit and track parcels you are authorized to transfer.'
          : 'Browse transfer requests available to your account.'}
        title="Transfer requests"
      />

      {isCitizen ? (
        <section className="registry-panel" aria-labelledby="new-transfer-heading">
          <h2 id="new-transfer-heading">New transfer request</h2>
          {parcelLoadError ? <p className="registry-state error-state" role="alert">{parcelLoadError}</p> : null}
          {submitError ? <p className="registry-state error-state" role="alert">{submitError}</p> : null}
          {submittedTransfer ? (
            <p className="registry-state" role="status">
              {submittedTransfer.status === 'SUBMITTED'
                ? `Transfer request ${submittedTransfer.request_id} was submitted. It is awaiting review; approval does not complete a blockchain transfer.`
                : `The application recorded transfer request ${submittedTransfer.request_id} with status ${transferStatusLabel(submittedTransfer.status)}.`}
              {' '}
              <Link to={`/transfers/${encodeURIComponent(submittedTransfer.request_id)}`}>
                View request
              </Link>
            </p>
          ) : null}
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
      ) : null}

      <section className="registry-panel" aria-labelledby="transfer-list-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="transfer-list-heading">
              {isCitizen ? 'Your transfer requests' : 'Transfer requests'}
            </h2>
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