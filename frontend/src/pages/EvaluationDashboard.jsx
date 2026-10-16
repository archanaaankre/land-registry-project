import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { getAccessToken, logoutUser } from '../services/authService.js'
import '../evaluation.css'
import {
  getAccessControlSummary,
  getOwnershipTraceability,
  measureApiPerformance,
} from '../services/evaluationService.js'
import MetricCard from '../components/evaluation/MetricCard.jsx'
import TamperDetectionChart from '../components/evaluation/TamperDetectionChart.jsx'
import DocumentIntegrityChart from '../components/evaluation/DocumentIntegrityChart.jsx'
import AccessControlSummary from '../components/evaluation/AccessControlSummary.jsx'
import OwnershipTimeline from '../components/evaluation/OwnershipTimeline.jsx'
import PerformanceChart from '../components/evaluation/PerformanceChart.jsx'

export default function EvaluationDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [traceability, setTraceability] = useState(null)
  const [traceabilityLoading, setTraceabilityLoading] = useState(true)
  const [traceabilityError, setTraceabilityError] = useState('')
  const [traceabilityReloadKey, setTraceabilityReloadKey] = useState(0)

  const [performance, setPerformance] = useState(null)
  const [performanceLoading, setPerformanceLoading] = useState(false)
  const [performanceError, setPerformanceError] = useState('')
  const [hasMeasured, setHasMeasured] = useState(false)

  const accessControl = getAccessControlSummary()

  const loadTraceability = useCallback(async (signal) => {
    const token = getAccessToken()
    setTraceabilityLoading(true)
    setTraceabilityError('')
    try {
      const result = await getOwnershipTraceability({ token, signal })
      if (signal.aborted) {
        return
      }
      setTraceability(result)
    } catch (error) {
      if (error?.name === 'AbortError' || signal.aborted) {
        return
      }
      if (error?.status === 401) {
        logoutUser()
        logout()
        navigate('/login', { replace: true })
        return
      }
      setTraceability(null)
      setTraceabilityError(error?.message ?? 'Could not load ownership traceability.')
    } finally {
      if (!signal.aborted) {
        setTraceabilityLoading(false)
      }
    }
  }, [logout, navigate])

  const runPerformanceMeasurement = useCallback(async (signal) => {
    const token = getAccessToken()
    setPerformanceLoading(true)
    setPerformanceError('')
    try {
      const result = await measureApiPerformance({ token, signal })
      if (signal.aborted) {
        return
      }
      setPerformance(result)
      setHasMeasured(true)
    } catch (error) {
      if (error?.name === 'AbortError' || signal.aborted) {
        return
      }
      if (error?.status === 401) {
        logoutUser()
        logout()
        navigate('/login', { replace: true })
        return
      }
      setPerformanceError(error?.message ?? 'Could not measure API performance.')
    } finally {
      if (!signal.aborted) {
        setPerformanceLoading(false)
      }
    }
  }, [logout, navigate])

  useEffect(() => {
    const controller = new AbortController()
    Promise.resolve().then(() => loadTraceability(controller.signal))
    return () => controller.abort()
  }, [loadTraceability, traceabilityReloadKey])

  function retryTraceability() {
    setTraceabilityLoading(true)
    setTraceabilityError('')
    setTraceability(null)
    setTraceabilityReloadKey((current) => current + 1)
  }

  function measurePerformance() {
    const controller = new AbortController()
    runPerformanceMeasurement(controller.signal)
  }

  const parcelCount = traceability?.parcels?.length ?? null
  const eventCount = traceability?.events?.length ?? null
  const successRate = performance?.summary?.successRatePercent

  return (
    <main className="evaluation-page">
      <header className="registry-header">
        <div>
          <p className="eyebrow">Evaluation &amp; security</p>
          <h1>Evaluation & Security Dashboard</h1>
          <p className="registry-intro">
            Controlled evaluation of the implemented land-registry API. Metrics are derived from real backend responses
            or documented unavailable states; no measured results are fabricated.
          </p>
        </div>
        <Link className="text-link" to="/dashboard">
          Back to account
        </Link>
      </header>

      <section className="registry-panel evaluation-methodology-panel" aria-labelledby="methodology-heading">
        <h2 id="methodology-heading">Evaluation scope and method</h2>
        <p>
          This dashboard reports only implemented capabilities: authenticated API calls, parcel and ownership record
          reads, configured authorization rules, and browser-measured API response times. Tamper detection, document
          hashing/verification, transfer transactions, and blockchain integration are not implemented in the current
          build and are shown as unavailable rather than as zero or successful results.
        </p>
        <dl className="identity-details">
          <div>
            <dt>Signed-in role</dt>
            <dd>{user?.role}</dd>
          </div>
          <div>
            <dt>Session ID source</dt>
            <dd>Protected by the existing JWT session context; API calls use the user’s token.</dd>
          </div>
        </dl>
      </section>

      <section className="summary-grid" aria-label="Summary metrics">
        <MetricCard
          detail="Loaded from GET /api/parcels when the registry repository is configured."
          status={traceabilityLoading ? undefined : parcelCount !== null ? 'success' : 'unavailable'}
          title="Parcel records loaded"
          unavailable={!traceabilityLoading && parcelCount === null}
          value={traceabilityLoading ? 'Loading…' : parcelCount}
        />
        <MetricCard
          detail="Ownership rows loaded across parcel histories."
          status={traceabilityLoading ? undefined : eventCount !== null ? 'success' : 'unavailable'}
          title="Ownership records loaded"
          unavailable={!traceabilityLoading && eventCount === null}
          value={traceabilityLoading ? 'Loading…' : eventCount}
        />
        <MetricCard
          detail="Computed from sampled API requests."
          status={hasMeasured && Number.isFinite(successRate) ? 'success' : 'unavailable'}
          title="API request success rate"
          unavailable={!hasMeasured || !Number.isFinite(successRate)}
          unit="%"
          value={successRate}
        />
        <MetricCard
          detail="No blockchain network is integrated or measured."
          status="unavailable"
          title="Blockchain performance"
          unavailable
          value="Not measured"
        />
      </section>

      <TamperDetectionChart />
      <DocumentIntegrityChart />
      <AccessControlSummary summary={accessControl} />
      <OwnershipTimeline
        data={traceability}
        error={traceabilityError}
        loading={traceabilityLoading}
        onRetry={retryTraceability}
      />
      <PerformanceChart
        data={performance}
        error={performanceError}
        loading={performanceLoading}
        onMeasure={measurePerformance}
      />

      <section className="registry-panel evaluation-definition" aria-labelledby="limitations-heading">
        <h2 id="limitations-heading">Test methodology and limitations</h2>
        <ul>
          <li>Original, modified, tamper, and document-integrity datasets are not implemented; those sections are intentionally unavailable.</li>
          <li>RBAC data lists configured backend roles and policy rules; no unauthorized-attempt test report is exposed.</li>
          <li>Ownership history is built only from exposed parcel and ownership-read endpoints and is ordered by recorded creation time.</li>
          <li>Performance values are browser-measured HTTP response times for sequential, non-destructive requests. They are not transaction throughput or blockchain finality measurements.</li>
          <li>Backend registry calls return an unavailable state when the PostgreSQL repository is not configured, which is reported rather than hidden.</li>
        </ul>
      </section>
    </main>
  )
}