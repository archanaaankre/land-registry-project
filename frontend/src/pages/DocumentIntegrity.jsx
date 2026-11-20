import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import {
  downloadSupportingDocument,
  listDocumentHashes,
  listSupportingDocuments,
  storeDocumentHash,
  uploadSupportingDocument,
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
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const canCreateTrustedHash = user?.role === 'REGISTRAR'
  const canUploadSupporting = ['REGISTRAR', 'VERIFICATION_OFFICER', 'CITIZEN'].includes(user?.role)

  // Supporting-document upload form state
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadDocumentName, setUploadDocumentName] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)

  // Trusted-hash form state
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

  // Supporting-documents review state
  const [supportingDocuments, setSupportingDocuments] = useState([])
  const [supportingLoading, setSupportingLoading] = useState(true)
  const [supportingError, setSupportingError] = useState('')
  const [downloadingDocId, setDownloadingDocId] = useState('')

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

  const loadSupportingDocuments = useCallback(async (signal) => {
    setSupportingLoading(true)
    setSupportingError('')
    try {
      const { data } = await listSupportingDocuments({ signal })
      if (!signal.aborted) {
        setSupportingDocuments(data.documents ?? [])
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
        setSupportingDocuments([])
        setSupportingError(
          requestError.message ||
            'We couldn’t load supporting documents. Please try again.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setSupportingLoading(false)
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    async function load() {
      await loadSupportingDocuments(controller.signal)
    }
    const controller = new AbortController()
    load()
    return () => controller.abort()
  }, [loadSupportingDocuments, reloadKey])

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

  async function handleUploadDocument(event) {
    event.preventDefault()
    if (uploading) return
    if (!uploadFile || !uploadDocumentName.trim()) {
      setUploadError('Please select a document and enter a name.')
      return
    }
    setUploading(true)
    setUploadError('')
    const formData = new FormData()
    formData.append('document', uploadFile)
    formData.append('document_name', uploadDocumentName.trim())
    try {
      const { data } = await uploadSupportingDocument(formData)
      setUploadResult(data.upload)
      setUploadFile(null)
      setUploadDocumentName('')
      setUploadOpen(false)
    } catch (requestError) {
      setUploadError(
        requestError.message || 'The supporting document could not be uploaded. Please try again.',
      )
    } finally {
      setUploading(false)
    }
  }

  async function handleDownloadSupportingDocument(documentId) {
    setDownloadingDocId(documentId)
    try {
      const { data } = await downloadSupportingDocument(documentId)
      const url = URL.createObjectURL(data.data)
      const link = document.createElement('a')
      link.href = url
      link.download = data.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (requestError) {
      setSupportingError(
        requestError.message ||
          'The supporting document could not be downloaded. Please try again.',
      )
    } finally {
      setDownloadingDocId('')
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
        intro="View stored document hashes, upload supporting documents, and verify documents against trusted hashes."
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

      {uploadResult && (
        <section className="registry-state parcel-success" role="status">
          <p>
            Supporting document uploaded: <strong>{uploadResult.document_name}</strong>
            {' '}(calculated hash: {uploadResult.calculated_hash}). This is not a trusted baseline.
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

      {canCreateTrustedHash && (
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
      )}

      {canUploadSupporting && (
      <section className="registry-panel" aria-labelledby="upload-supporting-heading">
        <div className="registry-toolbar">
          <div>
            <h2 id="upload-supporting-heading">Upload a supporting document</h2>
            <p className="result-count">
              Upload a document and calculate its SHA-256 hash without creating a trusted baseline.
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={() => setUploadOpen((open) => !open)}
            type="button"
          >
            {uploadOpen ? 'Close form' : 'Upload supporting document'}
          </button>
        </div>

        {uploadOpen && (
          <section className="registry-state parcel-registration-form" aria-labelledby="upload-form-heading">
            <h3 id="upload-form-heading">Supporting document</h3>
            {uploadError && (
              <p className="registry-state error-state" role="alert">{uploadError}</p>
            )}
            <form className="auth-form" onSubmit={handleUploadDocument}>
              <label>
                Document file
                <input
                  accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  required
                  type="file"
                />
              </label>
              <label>
                Document name
                <input
                  autoComplete="off"
                  maxLength={200}
                  onChange={(event) => setUploadDocumentName(event.target.value)}
                  required
                  type="text"
                  value={uploadDocumentName}
                />
              </label>
              <div className="parcel-registration-actions">
                <button className="primary-button" disabled={uploading} type="submit">
                  {uploading ? 'Uploading…' : 'Upload document'}
                </button>
                <button
                  className="secondary-button"
                  disabled={uploading}
                  onClick={() => setUploadOpen(false)}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </form>
          </section>
        )}
      </section>
      )}

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

      <section
        className="registry-panel"
        aria-labelledby="supporting-documents-heading"
      >
        <div className="registry-toolbar">
          <div>
            <h2 id="supporting-documents-heading">Supporting documents</h2>
            <p className="result-count">
              Supporting documents stored for later review.
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={() => loadSupportingDocuments(new AbortController().signal)}
            type="button"
          >
            Refresh
          </button>
        </div>

        {supportingLoading && (
          <p className="registry-state" role="status">
            Loading supporting documents…
          </p>
        )}
        {supportingError && (
          <p className="registry-state error-state" role="alert">
            {supportingError}
          </p>
        )}
        {!supportingLoading &&
          !supportingError &&
          supportingDocuments.length === 0 && (
            <p className="registry-state">
              No supporting documents are visible.
            </p>
          )}
        {!supportingLoading &&
          !supportingError &&
          supportingDocuments.length > 0 && (
            <div className="ownership-list">
              {supportingDocuments.map((doc) => (
                <article
                  className="ownership-record"
                  key={doc.supporting_document_id}
                >
                  <dl>
                    <div>
                      <dt>Document</dt>
                      <dd>{doc.document_name}</dd>
                    </div>
                    <div>
                      <dt>Supporting document ID</dt>
                      <dd>{doc.supporting_document_id}</dd>
                    </div>
                    <div>
                      <dt>SHA-256</dt>
                      <dd>{doc.document_hash}</dd>
                    </div>
                    <div>
                      <dt>Parcel ID</dt>
                      <dd>{doc.parcel_id || 'Not specified'}</dd>
                    </div>
                    <div>
                      <dt>Transfer request</dt>
                      <dd>{doc.transfer_request_id || 'Not specified'}</dd>
                    </div>
                    <div>
                      <dt>Uploaded by</dt>
                      <dd>{doc.uploaded_by}</dd>
                    </div>
                    <div>
                      <dt>Uploaded at</dt>
                      <dd>{formatTimestamp(doc.uploaded_at)}</dd>
                    </div>
                  </dl>
                  <button
                    className="secondary-button"
                    disabled={downloadingDocId === doc.supporting_document_id}
                    onClick={() =>
                      handleDownloadSupportingDocument(doc.supporting_document_id)
                    }
                    type="button"
                  >
                    {downloadingDocId === doc.supporting_document_id
                      ? 'Downloading…'
                      : 'Download'}
                  </button>
                </article>
              ))}
            </div>
          )}
      </section>
    </main>
  )
}
