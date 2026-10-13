import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listParcels } from '../services/parcelService.js'

function describeParcelLoadError(error) {
  if (error.status === 503 || error.code === 'registry_unavailable') {
    return 'The parcel registry is temporarily unavailable. Its repository or persistence may not be configured yet.'
  }
  return error.message
}

export default function Parcels() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [parcels, setParcels] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    listParcels({ signal: controller.signal })
      .then(setParcels)
      .catch((requestError) => {
        if (requestError.name === 'AbortError') {
          return
        }
        if (requestError.status === 401) {
          logout()
          navigate('/login', { replace: true })
          return
        }
        setError(describeParcelLoadError(requestError))
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [logout, navigate, reloadKey])

  const filteredParcels = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) {
      return parcels
    }
    return parcels.filter((parcel) =>
      [
        parcel.parcel_id,
        parcel.cadastral_number,
        parcel.location,
        parcel.status,
        parcel.area_unit,
      ].some((value) => String(value ?? '').toLowerCase().includes(normalizedQuery)),
    )
  }, [parcels, query])

  function retryLoadingParcels() {
    setLoading(true)
    setError('')
    setReloadKey((current) => current + 1)
  }

  return (
    <main className="registry-page">
      <header className="registry-header">
        <div>
          <p className="eyebrow">Land Registry</p>
          <h1>Parcel registry</h1>
          <p className="registry-intro">Browse registered parcels and their recorded details.</p>
        </div>
        <Link className="text-link" to="/dashboard">Back to dashboard</Link>
      </header>

      <section className="registry-panel" aria-labelledby="parcels-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="parcels-heading">Parcels</h2>
            {!loading && !error && (
              <p className="result-count">
                {filteredParcels.length} {filteredParcels.length === 1 ? 'parcel' : 'parcels'}
              </p>
            )}
          </div>
          <label className="search-field">
            <span>Search parcels</span>
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="ID, cadastral number, location, status…"
              type="search"
              value={query}
            />
          </label>
        </div>

        {loading && <p className="registry-state" role="status">Loading parcels…</p>}
        {!loading && error && (
          <div className="registry-state error-state" role="alert">
            <p>{error}</p>
            <button
              className="secondary-button"
              onClick={retryLoadingParcels}
              type="button"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && parcels.length === 0 && (
          <p className="registry-state">No parcels are currently available.</p>
        )}
        {!loading && !error && parcels.length > 0 && filteredParcels.length === 0 && (
          <p className="registry-state">No parcels match that search.</p>
        )}
        {!loading && !error && filteredParcels.length > 0 && (
          <div className="parcel-grid">
            {filteredParcels.map((parcel) => (
              <article className="parcel-card" key={parcel.parcel_id}>
                <div className="parcel-card-heading">
                  <span className={`status-badge status-${String(parcel.status).toLowerCase()}`}>
                    {parcel.status}
                  </span>
                  <h3>{parcel.cadastral_number}</h3>
                  <p className="parcel-id">ID: {parcel.parcel_id}</p>
                </div>
                <dl className="parcel-summary">
                  <div>
                    <dt>Location</dt>
                    <dd>{parcel.location}</dd>
                  </div>
                  <div>
                    <dt>Area</dt>
                    <dd>{parcel.area} {parcel.area_unit}</dd>
                  </div>
                </dl>
                <Link className="parcel-link" to={`/parcels/${encodeURIComponent(parcel.parcel_id)}`}>
                  View parcel details <span aria-hidden="true">→</span>
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
