import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listParcels, getParcelOwnership } from '../services/parcelService.js'
import { createOwnership } from '../services/ownershipService.js'
import {
  OWNERSHIP_STATUSES,
  activeShare,
  generateOwnershipId,
  validateOwnershipForm,
} from '../services/ownershipValidation.js'
import PageHeader from '../components/layout/PageHeader.jsx'

const EMPTY_FORM = {
  ownership_id: '',
  owner_id: '',
  share: '100',
  status: 'ACTIVE',
}

function describeLoadError(kind) {
  return kind === 'ownership'
    ? 'We couldn’t load the ownership records. Please try again.'
    : 'We couldn’t load the land records. Please try again.'
}

export default function OwnershipCreate() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [parcels, setParcels] = useState([])
  const [parcelsLoading, setParcelsLoading] = useState(true)
  const [parcelsError, setParcelsError] = useState('')
  const [selectedParcelId, setSelectedParcelId] = useState('')
  const [form, setForm] = useState(() => ({
    ...EMPTY_FORM,
    ownership_id: generateOwnershipId(),
  }))
  const [ownership, setOwnership] = useState({ parcelId: '', items: [], error: '' })
  const [ownershipReloadKey, setOwnershipReloadKey] = useState(0)
  const [parcelsReloadKey, setParcelsReloadKey] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [success, setSuccess] = useState('')

  const selectedParcel = useMemo(
    () => parcels.find((parcel) => parcel.parcel_id === selectedParcelId) ?? null,
    [parcels, selectedParcelId],
  )

  useEffect(() => {
    const controller = new AbortController()

    listParcels({ signal: controller.signal })
      .then((items) => {
        if (!controller.signal.aborted) {
          setParcels(items)
        }
      })
      .catch((requestError) => {
        if (requestError.name === 'AbortError') {
          return
        }
        if (requestError.status === 401) {
          logout()
          navigate('/login', { replace: true })
          return
        }
        setParcelsError(describeLoadError('parcels'))
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setParcelsLoading(false)
        }
      })

    return () => controller.abort()
  }, [logout, navigate, parcelsReloadKey])

  useEffect(() => {
    if (!selectedParcelId) {
      return undefined
    }

    const controller = new AbortController()

    getParcelOwnership(selectedParcelId, { signal: controller.signal })
      .then((items) => {
        if (!controller.signal.aborted) {
          setOwnership({ parcelId: selectedParcelId, items, error: '' })
        }
      })
      .catch((requestError) => {
        if (requestError.name === 'AbortError') {
          return
        }
        if (requestError.status === 401) {
          logout()
          navigate('/login', { replace: true })
          return
        }
        setOwnership({
          parcelId: selectedParcelId,
          items: [],
          error: describeLoadError('ownership'),
        })
      })

    return () => controller.abort()
  }, [logout, navigate, selectedParcelId, ownershipReloadKey])

  const ownershipForCurrentParcel =
    ownership.parcelId === selectedParcelId ? ownership : null
  const ownershipItems = useMemo(
    () => ownershipForCurrentParcel?.items ?? [],
    [ownershipForCurrentParcel],
  )
  const ownershipError = ownershipForCurrentParcel?.error ?? ''
  const ownershipLoading =
    selectedParcelId !== '' && ownershipForCurrentParcel === null

  const recordedActiveShare = useMemo(
    () => activeShare(ownershipItems),
    [ownershipItems],
  )
  const pendingShare = Number(form.share) || 0
  const shareExceeds =
    form.status === 'ACTIVE' &&
    Number.isFinite(pendingShare) &&
    recordedActiveShare + pendingShare > 100

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    setSubmitError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting) {
      return
    }

    setSubmitError('')
    setSuccess('')
    const result = validateOwnershipForm({
      ...form,
      parcel_id: selectedParcelId,
    })
    if (!result.ok) {
      setSubmitError(result.error)
      return
    }

    setSubmitting(true)
    try {
      const ownershipRecord = await createOwnership(result.payload)
      setSuccess(
        `Ownership record ${ownershipRecord.ownership_id} was recorded for parcel ${ownershipRecord.parcel_id}.`,
      )
      setForm({ ...EMPTY_FORM, ownership_id: generateOwnershipId() })
      setOwnershipReloadKey((current) => current + 1)
      setParcelsReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setSubmitError(
        requestError.message ||
          'Ownership could not be recorded. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="registry-page">
      <PageHeader
        actions={<Link className="text-link" to="/parcels">Back to parcels</Link>}
        eyebrow="Land Registry"
        intro="Record the initial ownership of a registered parcel."
        title="Record ownership"
      />

      <section className="registry-panel" aria-labelledby="ownership-form-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="ownership-form-heading">New ownership record</h2>
            <p className="result-count">
              Select a parcel, then enter the initial owner’s details.
            </p>
          </div>
        </div>

        <p className="registry-state" role="note">
          Recording ownership writes the entry to the registry database. It does
          not submit or confirm a blockchain transaction, and it is not proof of
          legal title.
        </p>

        {success && (
          <p className="registry-state parcel-success" role="status">
            {success}
          </p>
        )}

        {parcelsLoading ? (
          <p className="registry-state" role="status">Loading parcels…</p>
        ) : parcelsError ? (
          <div className="registry-state error-state" role="alert">
            <p>{parcelsError}</p>
            <button
              className="secondary-button"
              onClick={() => {
                setParcelsLoading(true)
                setParcelsError('')
                setParcelsReloadKey((current) => current + 1)
              }}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : parcels.length === 0 ? (
          <div className="registry-state">
            <p>No parcels are currently available. Register a parcel first.</p>
            <Link className="text-link" to="/parcels">Go to parcels</Link>
          </div>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            {submitError && (
              <p className="registry-state error-state" role="alert">
                {submitError}
              </p>
            )}

            <label>
              Parcel
              <select
                required
                value={selectedParcelId}
                onChange={(event) => setSelectedParcelId(event.target.value)}
              >
                <option value="">Select a parcel</option>
                {parcels.map((parcel) => (
                  <option key={parcel.parcel_id} value={parcel.parcel_id}>
                    {parcel.cadastral_number} — {parcel.location} ({parcel.parcel_id}, {parcel.status})
                  </option>
                ))}
              </select>
            </label>

            {selectedParcel && (
              <p className="registry-state" role="status">
                Selected parcel: <strong>{selectedParcel.cadastral_number}</strong>{' '}
                <span className={`status-badge status-${String(selectedParcel.status).toLowerCase()}`}>
                  {selectedParcel.status}
                </span>
                {ownershipLoading
                  ? ' — loading recorded ownership…'
                  : ownershipError
                    ? ''
                    : ` — ${recordedActiveShare}% active ownership share recorded`}
              </p>
            )}

            <label>
              Ownership ID
              <input
                autoComplete="off"
                disabled={submitting}
                required
                type="text"
                value={form.ownership_id}
                onChange={(event) => updateField('ownership_id', event.target.value)}
              />
            </label>

            <label>
              Owner ID (citizen user ID)
              <input
                autoComplete="off"
                disabled={submitting}
                placeholder="e.g. citizen-1"
                required
                type="text"
                value={form.owner_id}
                onChange={(event) => updateField('owner_id', event.target.value)}
              />
            </label>
            <p className="result-count">
              The owner must be an existing citizen account. Ownership is recorded
              against this ID.
            </p>

            <label>
              Ownership share (%)
              <input
                disabled={submitting}
                max={100}
                min={0}
                required
                step="any"
                type="number"
                value={form.share}
                onChange={(event) => updateField('share', event.target.value)}
              />
            </label>

            <label>
              Status
              <select
                disabled={submitting}
                value={form.status}
                onChange={(event) => updateField('status', event.target.value)}
              >
                {OWNERSHIP_STATUSES.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </label>
            <p className="result-count">
              ACTIVE is current ownership; INACTIVE and DISPUTED record history or a
              contested state.
            </p>

            {shareExceeds && (
              <p className="registry-state error-state" role="alert">
                Recorded active shares total {recordedActiveShare}%; adding {pendingShare}%
                would exceed 100%.
              </p>
            )}

            <div className="parcel-registration-actions">
              <button
                className="primary-button"
                disabled={submitting || shareExceeds}
                type="submit"
              >
                {submitting ? 'Recording…' : 'Record ownership'}
              </button>
              <button
                className="secondary-button"
                disabled={submitting}
                onClick={() => {
                  setForm({
                    ...EMPTY_FORM,
                    ownership_id: generateOwnershipId(),
                  })
                  setSubmitError('')
                }}
                type="button"
              >
                Reset
              </button>
            </div>
          </form>
        )}
      </section>

      {selectedParcel && (
        <section className="registry-panel ownership-panel" aria-labelledby="recorded-ownership-heading">
          <div className="registry-toolbar">
            <div>
              <h2 id="recorded-ownership-heading">Recorded ownership</h2>
              <p className="result-count">
                Active and historical records for this parcel
              </p>
            </div>
          </div>
          {ownershipLoading ? (
            <p className="registry-state" role="status">Loading ownership records…</p>
          ) : ownershipError ? (
            <div className="error-state" role="alert">
              <p>{ownershipError}</p>
              <button
                className="secondary-button"
                onClick={() => setOwnershipReloadKey((current) => current + 1)}
                type="button"
              >
                Retry
              </button>
            </div>
          ) : ownershipItems.length === 0 ? (
            <p className="registry-state">No ownership records are currently available.</p>
          ) : (
            <div className="ownership-list">
              {ownershipItems.map((record) => (
                <article className="ownership-record" key={record.ownership_id}>
                  <span className={`status-badge status-${String(record.status).toLowerCase()}`}>
                    {record.status}
                  </span>
                  <dl>
                    <div><dt>Ownership record</dt><dd>{record.ownership_id}</dd></div>
                    <div><dt>Owner ID</dt><dd>{record.owner_id}</dd></div>
                    <div><dt>Share</dt><dd>{record.share}%</dd></div>
                    <div><dt>Created</dt><dd>{new Date(record.created_at).toLocaleString()}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  )
}
