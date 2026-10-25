import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { getParcel, getParcelOwnership } from '../services/parcelService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

function describeLoadError(kind) {
  return kind === 'ownership'
    ? 'We couldn’t load ownership history. Please try again.'
    : 'We couldn’t load this parcel. Please try again.'
}

export default function ParcelDetails() {
  const { parcelId } = useParams()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [parcel, setParcel] = useState(null)
  const [ownership, setOwnership] = useState([])
  const [parcelError, setParcelError] = useState('')
  const [ownershipError, setOwnershipError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [loadedForParcelId, setLoadedForParcelId] = useState('')

  const loadDetails = useCallback(async (signal) => {
    const [parcelResult, ownershipResult] = await Promise.allSettled([
      getParcel(parcelId, { signal }),
      getParcelOwnership(parcelId, { signal }),
    ])

    if (signal.aborted) {
      return
    }

    const unauthorized = [parcelResult, ownershipResult].some(
      (result) => result.status === 'rejected' && result.reason.status === 401,
    )
    if (unauthorized) {
      logout()
      navigate('/login', { replace: true })
      return
    }

    setParcelError('')
    setOwnershipError('')
    if (parcelResult.status === 'fulfilled') {
      setParcel(parcelResult.value)
    } else {
      setParcel(null)
      if (parcelResult.reason.name !== 'AbortError') {
        setParcelError(describeLoadError('parcel'))
      }
    }

    if (ownershipResult.status === 'fulfilled') {
      setOwnership(ownershipResult.value)
    } else {
      setOwnership([])
      if (ownershipResult.reason.name !== 'AbortError') {
        setOwnershipError(describeLoadError('ownership'))
      }
    }
    setLoadedForParcelId(parcelId)
    setLoading(false)
  }, [logout, navigate, parcelId])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => loadDetails(controller.signal))
    return () => controller.abort()
  }, [loadDetails, reloadKey])

  function retryLoadingDetails() {
    setLoading(true)
    setParcelError('')
    setOwnershipError('')
    setParcel(null)
    setOwnership([])
    setLoadedForParcelId('')
    setReloadKey((current) => current + 1)
  }

  const isLoading = loading || loadedForParcelId !== parcelId
  const isCurrentOwner = ownership.some(
    (record) => record.status === 'ACTIVE' && record.owner_id === user?.id,
  )

  return (
    <main className="registry-page">
      <PageHeader
        actions={<Link className="text-link" to="/parcels">Back to parcels</Link>}
        eyebrow="Land Registry"
        intro={`Parcel identifier: ${parcelId}`}
        title="Parcel details"
      />

      {isLoading && <p className="registry-state registry-panel" role="status">Loading parcel details…</p>}
      {!isLoading && (
        <>
          {parcelError ? (
            <section className="registry-panel error-state" role="alert">
              <p>{parcelError}</p>
              <button
                className="secondary-button"
                onClick={retryLoadingDetails}
                type="button"
              >
                Retry
              </button>
            </section>
          ) : parcel && (
            <section className="registry-panel" aria-labelledby="parcel-summary-heading">
              <div className="details-heading">
                <div>
                  <p className="eyebrow">Cadastral number</p>
                  <h2 id="parcel-summary-heading">{parcel.cadastral_number}</h2>
                </div>
                <span className={`status-badge status-${String(parcel.status).toLowerCase()}`}>
                  {parcel.status}
                </span>
              </div>
              <dl className="details-grid">
                <div><dt>Parcel ID</dt><dd>{parcel.parcel_id}</dd></div>
                <div><dt>Location</dt><dd>{parcel.location}</dd></div>
                <div><dt>Area</dt><dd>{parcel.area} {parcel.area_unit}</dd></div>
                <div><dt>Created</dt><dd>{new Date(parcel.created_at).toLocaleString()}</dd></div>
                <div><dt>Last updated</dt><dd>{new Date(parcel.updated_at).toLocaleString()}</dd></div>
              </dl>
            </section>
          )}

          {parcel && (
            <section className="registry-panel ownership-panel" aria-labelledby="ownership-heading">
              <div className="registry-toolbar">
                <div>
                  <h2 id="ownership-heading">Recorded ownership</h2>
                  <p className="result-count">Ownership records associated with this parcel</p>
                </div>
              </div>
              {ownershipError ? (
                <div className="error-state" role="alert">
                  <p>{ownershipError}</p>
                  <button
                    className="secondary-button"
                    onClick={retryLoadingDetails}
                    type="button"
                  >
                    Retry
                  </button>
                </div>
              ) : ownership.length === 0 ? (
                <p className="registry-state">No ownership records are currently available.</p>
              ) : (
                <div className="ownership-list">
                  {ownership.map((record) => (
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
              {!ownershipError && user?.role === 'CITIZEN' && isCurrentOwner ? (
                <Link
                  className="primary-button"
                  state={{ parcelId: parcel.parcel_id }}
                  to="/transfers"
                >
                  Request a transfer
                </Link>
              ) : null}
            </section>
          )}
        </>
      )}
    </main>
  )
}
