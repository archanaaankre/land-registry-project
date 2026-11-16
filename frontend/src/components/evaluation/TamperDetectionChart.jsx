import { useCallback, useEffect, useState } from 'react'
import { getTamperDetectionSummary } from '../../services/evaluationService.js'

export default function TamperDetectionChart({ token }) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const loadSummary = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const data = await getTamperDetectionSummary({ token, signal })
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
          requestError.message || 'Tamper detection is unavailable.',
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
    <section className="evaluation-panel" aria-labelledby="tamper-detection-heading">
      <div className="evaluation-panel-heading">
        <h2 id="tamper-detection-heading">Tamper detection</h2>
        <p className="result-count">
          {loading ? 'Loading…' : summary ? `${summary.totalDocuments} document${summary.totalDocuments === 1 ? '' : 's'} analyzed` : 'Unavailable'}
        </p>
      </div>

      {loading ? (
        <p className="registry-state" role="status">Loading tamper detection data…</p>
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
              <p className="stat-detail">Documents analyzed</p>
            </div>
            <div className="stat-card">
              <h3>Verified</h3>
              <p className="stat-value">{summary.verified}</p>
              <p className="stat-detail">Hash matches trusted original</p>
            </div>
            <div className="stat-card">
              <h3>Modified</h3>
              <p className="stat-value">{summary.modified}</p>
              <p className="stat-detail">Hash does not match trusted original</p>
            </div>
            <div className="stat-card">
              <h3>Not verified</h3>
              <p className="stat-value">{summary.notVerified}</p>
              <p className="stat-detail">No verification performed yet</p>
            </div>
          </div>

          {summary.detectionRate !== null ? (
            <div className="evaluation-definition">
              <h3>Tamper detection rate</h3>
              <p className="stat-value">{summary.detectionRate}%</p>
              <p className="registry-state">
                Modified documents detected ({summary.modified}) out of
                documents tested ({summary.totalTested}).
              </p>
            </div>
          ) : null}

          <div className="evaluation-definition">
            <h3>Results required for a detection rate</h3>
            <dl className="definition-list">
              <div>
                <dt>Modified records tested</dt>
                <dd>{summary.totalTested}</dd>
              </div>
              <div>
                <dt>Correctly detected</dt>
                <dd>{summary.modified}</dd>
              </div>
              <div>
                <dt>Not detected / unexpected outcomes</dt>
                <dd>0</dd>
              </div>
              <div>
                <dt>Unmodified records tested</dt>
                <dd>{summary.verified}</dd>
              </div>
              <div>
                <dt>Denominator rule</dt>
                <dd>{summary.denominatorRule}</dd>
              </div>
            </dl>
          </div>
        </>
      )}
    </section>
  )
}
