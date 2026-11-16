import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { listDocumentHashes } from '../services/documentService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

const STATUS_LABELS = {
  MATCHED: 'Verified',
  MISMATCHED: 'Modified',
  NOT_VERIFIED: 'Not verified',
  UNAVAILABLE: 'Unavailable',
}

function formatTimestamp(value) {
  if (!value) {
    return 'Not available'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not available' : date.toLocaleString()
}

export default function TamperDetection() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadDocuments = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const { data } = await listDocumentHashes({ signal })
      if (!signal.aborted) {
        setDocuments(data.documents ?? [])
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
        setDocuments([])
        setError(
          requestError.message || 'We couldn’t load tamper detection data. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false)
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    async function load() {
      await loadDocuments(controller.signal)
    }
    const controller = new AbortController()
    load()
    return () => controller.abort()
  }, [loadDocuments, reloadKey])

  function reloadDocuments() {
    setError('')
    setReloadKey((current) => current + 1)
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  const verified = documents.filter(
    (d) => d.last_verification_status === 'MATCHED'
  ).length
  const modified = documents.filter(
    (d) => d.last_verification_status === 'MISMATCHED'
  ).length
  const notVerified = documents.filter(
    (d) => d.last_verification_status === null || d.last_verification_status === undefined
  ).length

  return (
    <main className="registry-page">
      <PageHeader
        eyebrow="Tamper detection"
        intro="Review document verification history to detect tampering. Documents are classified as verified, modified, or never verified."
        title="Tamper Detection"
      />

      <nav className="dashboard-links" aria-label="Account navigation">
        <div className="dashboard-navigation">
          <Link to="/dashboard">Back to account</Link>
        </div>
        <button className="secondary-button" onClick={handleLogout} type="button">
          Sign out
        </button>
      </nav>

      <section className="registry-panel" aria-labelledby="tamper-stats-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="tamper-stats-heading">Tamper detection summary</h2>
            <p className="result-count">
              Documents analyzed: {documents.length}
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={reloadDocuments}
            type="button"
          >
            Refresh
          </button>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <h3>Verified documents</h3>
            <p className="stat-value">{verified}</p>
            <p className="stat-detail">Hash matches trusted original</p>
          </div>
          <div className="stat-card">
            <h3>Modified documents</h3>
            <p className="stat-value">{modified}</p>
            <p className="stat-detail">Hash does not match trusted original</p>
          </div>
          <div className="stat-card">
            <h3>Never verified</h3>
            <p className="stat-value">{notVerified}</p>
            <p className="stat-detail">No verification performed yet</p>
          </div>
        </div>
      </section>

      {loading && <p className="registry-state" role="status">Loading documents…</p>}
      {!loading && error && (
        <div className="registry-state error-state" role="alert">
          <p>{error}</p>
          <button
            className="secondary-button"
            onClick={reloadDocuments}
            type="button"
          >
            Retry
          </button>
        </div>
      )}
      {!loading && !error && documents.length === 0 && (
        <p className="registry-state">No documents have been stored for tamper detection.</p>
      )}
      {!loading && !error && documents.length > 0 && (
        <section className="registry-panel" aria-labelledby="tamper-detail-heading">
          <div className="registry-toolbar">
            <div>
              <h2 id="tamper-detail-heading">Document verification detail</h2>
            </div>
          </div>
          <div className="ownership-list">
            {documents.map((doc) => {
              const status = doc.last_verification_status || 'NOT_VERIFIED'
              const statusClass = status === 'MATCHED' ? 'status-active' : status === 'MISMATCHED' ? 'status-failed' : 'status-inactive'
              return (
                <article className="ownership-record" key={doc.document_id}>
                  <span className={`status-badge ${statusClass}`}>
                    {STATUS_LABELS[status] || status}
                  </span>
                  <dl>
                    <div><dt>Document</dt><dd>{doc.document_name}</dd></div>
                    <div><dt>Document ID</dt><dd>{doc.document_id}</dd></div>
                    <div>
                      <dt>Trusted hash</dt>
                      <dd>{doc.document_hash}</dd>
                    </div>
                    <div>
                      <dt>Last verification</dt>
                      <dd>
                        {formatTimestamp(doc.last_verified_at) || 'Never verified'}
                      </dd>
                    </div>
                    <div>
                      <dt>Verification count</dt>
                      <dd>{doc.verification_count}</dd>
                    </div>
                    <div>
                      <dt>Parcel ID</dt>
                      <dd>{doc.parcel_id || 'Not specified'}</dd>
                    </div>
                  </dl>
                </article>
              )
            })}
          </div>
        </section>
      )}
    </main>
  )
}
