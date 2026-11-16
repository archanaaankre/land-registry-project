import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import {
  listDocumentHashes,
  storeDocumentHash,
  verifyDocument,
} from '../services/documentService.js'
import PageHeader from '../components/layout/PageHeader.jsx'

function formatTimestamp(value) {
  if (!value) {
    return 'Not available'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not available' : date.toLocaleString()
}

export default function DocumentIntegrity() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  // Upload/store form state
  const [storeOpen, setStoreOpen] = useState(false)
  const [storeFile, setStoreFile] = useState(null)
  const [storeDocumentName, setStoreDocumentName] = useState('')
  const [storeParcelId, setStoreParcelId] = useState('')
  const [storeError, setStoreError] = useState('')
  const [storing, setStoring] = useState(false)
  const [storedHash, setStoredHash] = useState(null)

  // Verify form state
  const [verifyDocId, setVerifyDocId] = useState('')
  const [verifyFile, setVerifyFile] = useState(null)
  const [verifyError, setVerifyError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [verificationResult, setVerificationResult] = useState(null)

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
          requestError.message || 'We couldn’t load document hashes. Please try again.',
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

  async function handleStoreDocument(event) {
    event.preventDefault()
    if (storing) return
    if (!storeFile || !storeDocumentName.trim()) {
      setStoreError('Please select a document and enter a name.')
      return
    }
    setStoring(true)
    setStoreError('')
    const formData = new FormData()
    formData.append('document', storeFile)
    formData.append('document_name', storeDocumentName.trim())
    if (storeParcelId.trim()) {
      formData.append('parcel_id', storeParcelId.trim())
    }
    try {
      const { data } = await storeDocumentHash(formData)
      const doc = data.document
      setStoredHash(doc)
      setStoreFile(null)
      setStoreDocumentName('')
      setStoreParcelId('')
      setStoreOpen(false)
      reloadDocuments()
    } catch (requestError) {
      setStoreError(
        requestError.message || 'The document hash could not be stored. Please try again.',
      )
    } finally {
      setStoring(false)
    }
  }

  async function handleVerifyDocument(event) {
    event.preventDefault()
    if (verifying) return
    if (!verifyDocId || !verifyFile) {
      setVerifyError('Please select a document and enter a document ID.')
      return
    }
    setVerifying(true)
    setVerifyError('')
    const formData = new FormData()
    formData.append('document', verifyFile)
    try {
      const { data } = await verifyDocument(verifyDocId, formData)
      setVerificationResult(data.verification)
      setVerifyFile(null)
    } catch (requestError) {
      setVerifyError(
        requestError.message || 'Document verification could not be completed. Please try again.',
      )
    } finally {
      setVerifying(false)
    }
  }

  return (
    <main className="registry-page">
      <PageHeader
        eyebrow="Document integrity"
        intro="Upload documents to store their trusted SHA-256 hash, or verify a document against a stored hash."
        title="Document Integrity"
      />

      <nav className="dashboard-links" aria-label="Account navigation">
        <div className="dashboard-navigation">
          <Link to="/dashboard">Back to account</Link>
        </div>
        <button className="secondary-button" onClick={handleLogout} type="button">
          Sign out
        </button>
      </nav>

      {storedHash && (
        <section className="registry-state parcel-success" role="status">
          <p>
            Document hash stored successfully: <strong>{storedHash.document_name}</strong>
            ({storedHash.document_hash})
          </p>
        </section>
      )}

      {verificationResult && (
        <section
          className={`registry-state ${
            verificationResult.match ? 'parcel-success' : 'error-state'
          }`}
          role={verificationResult.match ? 'status' : 'alert'}
        >
          <p>
            Verification result for <strong>{verificationResult.document_name}</strong>:{' '}
            {verificationResult.match
              ? 'VERIFIED — hash matches the trusted original.'
              : 'MODIFIED — calculated hash does not match the trusted original.'}
          </p>
          <p>
            Stored hash: {verificationResult.document_hash}<br />
            Calculated hash: {verificationResult.calculated_hash}
          </p>
        </section>
      )}

      <section className="registry-panel" aria-labelledby="store-document-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="store-document-heading">Store a document hash</h2>
            <p className="result-count">
              Calculate and store the trusted SHA-256 hash of a document.
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={() => setStoreOpen((open) => !open)}
            type="button"
          >
            {storeOpen ? 'Close form' : 'Upload document'}
          </button>
        </div>

        {storeOpen && (
          <section className="registry-state parcel-registration-form" aria-labelledby="store-form-heading">
            <h3 id="store-form-heading">Store Document Hash</h3>
            {storeError && (
              <p className="registry-state error-state" role="alert">{storeError}</p>
            )}
            <form className="auth-form" onSubmit={handleStoreDocument}>
              <label>
                Document file
                <input
                  accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null
                    setStoreFile(file)
                  }}
                  required
                  type="file"
                />
              </label>
              <label>
                Document name
                <input
                  autoComplete="off"
                  maxLength={200}
                  onChange={(event) => setStoreDocumentName(event.target.value)}
                  required
                  type="text"
                  value={storeDocumentName}
                />
              </label>
              <label>
                Parcel ID (optional)
                <input
                  autoComplete="off"
                  onChange={(event) => setStoreParcelId(event.target.value)}
                  type="text"
                  value={storeParcelId}
                />
              </label>
              <div className="parcel-registration-actions">
                <button className="primary-button" disabled={storing} type="submit">
                  {storing ? 'Storing…' : 'Store hash'}
                </button>
                <button
                  className="secondary-button"
                  disabled={storing}
                  onClick={() => setStoreOpen(false)}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </form>
          </section>
        )}
      </section>

      <section className="registry-panel" aria-labelledby="verify-document-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="verify-document-heading">Verify a document</h2>
            <p className="result-count">
              Compare a document&rsquo;s hash against its trusted stored hash.
            </p>
          </div>
        </div>

        <form className="auth-form" onSubmit={handleVerifyDocument}>
          <label>
            Document ID
            <input
              autoComplete="off"
              onChange={(event) => setVerifyDocId(event.target.value)}
              required
              type="text"
              value={verifyDocId}
            />
          </label>
          <label>
            Document file
            <input
              accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"
              onChange={(event) => {
                setVerifyFile(event.target.files?.[0] ?? null)
              }}
              required
              type="file"
            />
          </label>
          <div className="parcel-registration-actions">
            <button className="primary-button" disabled={verifying} type="submit">
              {verifying ? 'Verifying…' : 'Verify document'}
            </button>
          </div>
        </form>
        {verifyError && (
          <p className="registry-state error-state" role="alert">{verifyError}</p>
        )}
      </section>

      <section className="registry-panel" aria-labelledby="verification-history-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="verification-history-heading">Stored document hashes</h2>
            {!loading && !error && (
              <p className="result-count">
                {documents.length} document{documents.length === 1 ? '' : 's'}
              </p>
            )}
          </div>
          <button
            className="secondary-button"
            onClick={reloadDocuments}
            type="button"
          >
            Refresh
          </button>
        </div>

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
          <p className="registry-state">No document hashes are currently stored.</p>
        )}
        {!loading && !error && documents.length > 0 && (
          <div className="ownership-list">
            {documents.map((doc) => (
              <article className="ownership-record" key={doc.document_id}>
                <dl>
                  <div><dt>Document</dt><dd>{doc.document_name}</dd></div>
                  <div><dt>Document ID</dt><dd>{doc.document_id}</dd></div>
                  <div>
                    <dt>Trusted hash</dt>
                    <dd>{doc.document_hash}</dd>
                  </div>
                  <div><dt>Parcel ID</dt><dd>{doc.parcel_id || 'Not specified'}</dd></div>
                  <div><dt>Uploaded by</dt><dd>{doc.uploaded_by}</dd></div>
                  <div>
                    <dt>Uploaded at</dt>
                    <dd>{formatTimestamp(doc.uploaded_at)}</dd>
                  </div>
                  <div>
                    <dt>Last verified</dt>
                    <dd>
                      {formatTimestamp(doc.last_verified_at)}
                      {doc.last_verification_status ? ` (${doc.last_verification_status})` : ''}
                    </dd>
                  </div>
                  <div>
                    <dt>Verification count</dt>
                    <dd>{doc.verification_count}</dd>
                  </div>
                </dl>
                <button
                  className="secondary-button"
                  onClick={() => setVerifyDocId(doc.document_id)}
                  type="button"
                >
                  Verify this document
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
