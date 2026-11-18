import { useCallback, useEffect, useState } from 'react'
import { getDocumentIntegritySummary } from '../../services/evaluationService.js'

export default function DocumentIntegrityChart({ token }) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadSummary = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const data = await getDocumentIntegritySummary({ token, signal })
      if (!signal.aborted) {
        setSummary(data)
        setError('')
      }
    } catch (requestError) {
      if (requestError.name === 'AbortError' || signal.aborted) {
        return
      }
      if (!signal.aborted) {
        setSummary(null)
        setError(
          requestError.message || 'Document integrity verification is unavailable.',
        )
      }
    } finally {
      if (!signal.aborted) {
        setLoading(false)
      }
    }
  }, [token])

  useEffect(() => {
    async function init() {
      if (!token) {
        setLoading(false)
        return
      }
      const controller = new AbortController()
      await loadSummary(controller.signal)
    }
    init()
    return () => {}
  }, [token, loadSummary, reloadKey])

  function retry() {
    setError('')
    setReloadKey((current) => current + 1)
  }

  return (
    <section className="evaluation-panel" aria-labelledby="document-integrity-heading">
      <div className="evaluation-panel-heading">
        <h2 id="document-integrity-heading">Document integrity</h2>
        <p className="result-count">
          {loading ? 'Loading…' : summary ? `${summary.totalDocuments} document${summary.totalDocuments === 1 ? '' : 's'} tracked` : 'Unavailable'}
        </p>
      </div>

      {loading ? (
        <p className="registry-state" role="status">Loading document integrity data…</p>
      ) : error ? (
        <div className="registry-state error-state" role="alert">
          <p>{error}</p>
          <button className="secondary-button" onClick={retry} type="button">
            Retry
          </button>
        </div>
      ) : summary.status === 'unavailable' ? (
        <div className="unavailable-state" role="status">
          <strong>{summary.title}: unavailable</strong>
          <p>{summary.message}</p>
        </div>
      ) : (
        <>
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Total documents</h3>
              <p className="stat-value">{summary.totalDocuments}</p>
              <p className="stat-detail">Documents with stored hashes</p>
            </div>
            <div className="stat-card">
              <h3>Verified</h3>
              <p className="stat-value">{summary.matched}</p>
              <p className="stat-detail">Hash matches trusted original</p>
            </div>
            <div className="stat-card">
              <h3>Modified</h3>
              <p className="stat-value">{summary.mismatched}</p>
              <p className="stat-detail">Hash does not match trusted original</p>
            </div>
            <div className="stat-card">
              <h3>Not verified</h3>
              <p className="stat-value">{summary.notVerified}</p>
              <p className="stat-detail">No verification performed yet</p>
            </div>
          </div>

          <div className="evaluation-definition">
            <h3>Verification results</h3>
            <p className="registry-state">{summary.disclaimer}</p>
            <dl className="definition-list">
              <div>
                <dt>Matching document hashes</dt>
                <dd>{summary.matched}</dd>
              </div>
              <div>
                <dt>Modified documents with detected mismatches</dt>
                <dd>{summary.mismatched}</dd>
              </div>
              <div>
                <dt>Documents never verified</dt>
                <dd>{summary.notVerified}</dd>
              </div>
              <div>
                <dt>Detection-rate rule</dt>
                <dd>
                  Modified documents with a detected mismatch / documents tested × 100. Calculate only when
                  both counts are available and the tested count is greater than zero.
                </dd>
              </div>
            </dl>
          </div>
        </>
      )}
    </section>
  )
}
