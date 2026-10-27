import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { createParcel, listParcels } from '../services/parcelService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

const EMPTY_PARCEL = {
  parcel_id: '',
  cadastral_number: '',
  location: '',
  area: '',
  area_unit: '',
  status: '',
}

const AREA_UNITS = ['SQ_METERS', 'HECTARES', 'ACRES']
const PARCEL_STATUSES = ['ACTIVE', 'INACTIVE', 'DISPUTED']

function describeParcelLoadError() {
  return 'We couldn’t load the land records. Please try again.'
}

export default function Parcels() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [parcels, setParcels] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [registrationOpen, setRegistrationOpen] = useState(false)
  const [registrationData, setRegistrationData] = useState(EMPTY_PARCEL)
  const [registrationError, setRegistrationError] = useState('')
  const [registrationSuccess, setRegistrationSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)

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
        setError(describeParcelLoadError())
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

  async function handleRegisterParcel(event) {
    event.preventDefault()
    if (submitting) return

    const payload = {
      parcel_id: registrationData.parcel_id.trim(),
      cadastral_number: registrationData.cadastral_number.trim(),
      location: registrationData.location.trim(),
      area: Number(registrationData.area),
      area_unit: registrationData.area_unit,
      status: registrationData.status,
    }
    if (
      !payload.parcel_id ||
      !payload.cadastral_number ||
      !payload.location ||
      !registrationData.area ||
      !payload.area_unit ||
      !payload.status
    ) {
      setRegistrationError('Please complete all required fields.')
      return
    }
    if (!Number.isFinite(payload.area) || payload.area <= 0) {
      setRegistrationError('Area must be a number greater than zero.')
      return
    }

    setSubmitting(true)
    setRegistrationError('')
    setRegistrationSuccess('')
    try {
      const parcel = await createParcel(payload)
      setRegistrationSuccess(`Parcel ${parcel.parcel_id} was registered successfully.`)
      setRegistrationData(EMPTY_PARCEL)
      setRegistrationOpen(false)
      setLoading(true)
      setError('')
      setReloadKey((current) => current + 1)
    } catch (requestError) {
      if (requestError.status === 401) {
        logout()
        navigate('/login', { replace: true })
        return
      }
      setRegistrationError(
        requestError.message || 'The parcel could not be registered. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="registry-page">
      <PageHeader
        actions={<Link className="text-link" to="/dashboard">Back to dashboard</Link>}
        eyebrow="Land Registry"
        intro="Browse registered parcels and their recorded details."
        title="Parcel registry"
      />

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
          <div className="parcel-toolbar-actions">
            {user?.role === 'REGISTRAR' && (
              <button
                className="primary-button"
                onClick={() => {
                  setRegistrationOpen((open) => !open)
                  setRegistrationError('')
                }}
                type="button"
              >
                {registrationOpen ? 'Close form' : 'Register Parcel'}
              </button>
            )}
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
        </div>

        {registrationSuccess && (
          <p className="registry-state parcel-success" role="status">
            {registrationSuccess}
          </p>
        )}
        {registrationOpen && user?.role === 'REGISTRAR' && (
          <section className="registry-state parcel-registration-form" aria-labelledby="register-parcel-heading">
            <h3 id="register-parcel-heading">Register a parcel</h3>
            {registrationError && (
              <p className="registry-state error-state" role="alert">
                {registrationError}
              </p>
            )}
            <form className="auth-form" onSubmit={handleRegisterParcel}>
              <label>
                Parcel ID
                <input
                  autoComplete="off"
                  onChange={(event) =>
                    setRegistrationData((current) => ({
                      ...current,
                      parcel_id: event.target.value,
                    }))
                  }
                  required
                  type="text"
                  value={registrationData.parcel_id}
                />
              </label>
              <label>
                Cadastral number
                <input
                  onChange={(event) =>
                    setRegistrationData((current) => ({
                      ...current,
                      cadastral_number: event.target.value,
                    }))
                  }
                  required
                  type="text"
                  value={registrationData.cadastral_number}
                />
              </label>
              <label>
                Location
                <input
                  onChange={(event) =>
                    setRegistrationData((current) => ({
                      ...current,
                      location: event.target.value,
                    }))
                  }
                  required
                  type="text"
                  value={registrationData.location}
                />
              </label>
              <label>
                Area
                <input
                  min="0"
                  onChange={(event) =>
                    setRegistrationData((current) => ({
                      ...current,
                      area: event.target.value,
                    }))
                  }
                  required
                  step="any"
                  type="number"
                  value={registrationData.area}
                />
              </label>
              <label>
                Area unit
                <select
                  onChange={(event) =>
                    setRegistrationData((current) => ({
                      ...current,
                      area_unit: event.target.value,
                    }))
                  }
                  required
                  value={registrationData.area_unit}
                >
                  <option value="">Select an area unit</option>
                  {AREA_UNITS.map((unit) => (
                    <option key={unit} value={unit}>{unit}</option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select
                  onChange={(event) =>
                    setRegistrationData((current) => ({
                      ...current,
                      status: event.target.value,
                    }))
                  }
                  required
                  value={registrationData.status}
                >
                  <option value="">Select a status</option>
                  {PARCEL_STATUSES.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>
              <div className="parcel-registration-actions">
                <button className="primary-button" disabled={submitting} type="submit">
                  {submitting ? 'Registering…' : 'Register parcel'}
                </button>
                <button
                  className="secondary-button"
                  disabled={submitting}
                  onClick={() => {
                    setRegistrationOpen(false)
                    setRegistrationError('')
                  }}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </form>
          </section>
        )}

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
