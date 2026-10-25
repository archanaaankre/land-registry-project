import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'
import { getAccessToken, logoutUser } from '../services/authService.js'
import '../evaluation.css'
import { getAccessControlSummary, getOwnershipTraceability, measureApiPerformance } from '../services/evaluationService.js'
import PageHeader from '../components/layout/PageHeader.jsx'
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
      setTraceabilityError('We couldn’t load ownership history for this evaluation. Please try again.')
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
      setPerformanceError('The response-time measurement could not be completed. Please try again.')
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

  return (
    <main className="evaluation-page">
      <PageHeader
        actions={<Link className="text-link" to="/dashboard">Back to account</Link>}
        eyebrow="Evaluation & security"
        intro="A transparent summary of implemented data, measured API response times, and evaluation results that are not yet available. No results are fabricated."
        title="Evaluation & Security Dashboard"
      />

      <section className="registry-panel evaluation-methodology-panel" aria-labelledby="methodology-heading">
        <h2 id="methodology-heading">Evaluation scope and method</h2>
        <p>
          The dashboard separates configured policy from executed tests. API response times below are sampled from
          real authenticated requests; they are not transaction processing or blockchain confirmation measurements.
          No tamper-test results, document-hash results, access-control test outcomes, or blockchain transaction
          measurements are currently exposed by the application.
        </p>
        <dl className="identity-details">
          <div>
            <dt>Signed-in role</dt>
            <dd>{user?.role}</dd>
          </div>
          <div>
            <dt>Session context</dt>
            <dd>Protected by the existing JWT session context; API calls use the user’s token.</dd>
          </div>
        </dl>
      </section>

      <section className="summary-grid" aria-label="Evaluation summary metrics">
        <MetricCard
          detail="No modified-record evaluation runner or measured test results are available."
          state="unavailable"
          title="Tamper Detection"
        />
        <MetricCard
          detail="Document upload and hash verification are not implemented, so no documents have been tested."
          state="unavailable"
          title="Document Integrity"
        />
        <MetricCard
          detail="Authorization rules are configured, but no executed role-test results are exposed."
          state="unavailable"
          title="Access-Control Testing"
        />
        <MetricCard
          detail="No end-to-end land-transfer transaction test results are available."
          state="not-measured"
          title="Transaction Success Rate"
        />
        <MetricCard
          detail="Blockchain confirmation is not integrated or measured in this build."
          state="unavailable"
          title="Average Transaction Confirmation Time"
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

      <section className="evaluation-panel" aria-labelledby="comparison-heading">
        <div className="evaluation-panel-heading">
          <h2 id="comparison-heading">Traditional database and blockchain comparison</h2>
          <p className="result-count">Evidence status for project demonstration</p>
        </div>
        <p className="evaluation-context">
          This is a measurement-readiness comparison, not a claim that one storage approach performs or protects
          records better. No matched traditional-database versus blockchain experiment has been run.
        </p>
        <div className="permission-matrix-wrapper">
          <table className="permission-matrix comparison-matrix">
            <caption className="sr-only">
              Current evidence and comparison status for measurable land-registry properties.
            </caption>
            <thead>
              <tr>
                <th scope="col">Property</th>
                <th scope="col">Current project evidence</th>
                <th scope="col">Comparative result</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Audit-trail visibility</th>
                <td>Transfer request status history is available from the application API.</td>
                <td>Not yet measured under matched conditions.</td>
              </tr>
              <tr>
                <th scope="row">Modification detection</th>
                <td>No tamper-test or document-hash verification results are available.</td>
                <td>Not yet measured.</td>
              </tr>
              <tr>
                <th scope="row">Authorization enforcement</th>
                <td>Role rules are configured; executed test outcomes are not available.</td>
                <td>Not yet measured.</td>
              </tr>
              <tr>
                <th scope="row">Processing and confirmation time</th>
                <td>Browser-measured API response time is available separately; blockchain confirmation time is not.</td>
                <td>Not yet measured under matched conditions.</td>
              </tr>
              <tr>
                <th scope="row">Failure rate and throughput</th>
                <td>No transaction load-test dataset is available.</td>
                <td>Not yet measured.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="registry-panel evaluation-definition" aria-labelledby="limitations-heading">
        <h2 id="limitations-heading">Test methodology and limitations</h2>
        <ul>
          <li>Tamper detection, document verification, and access-control test outcomes require dedicated evaluation datasets that are not currently exposed.</li>
          <li>Ownership entries are read from parcel ownership records; they are not treated as transfer events or blockchain confirmations.</li>
          <li>API performance values are browser-measured response times for sequential requests. They are not transaction throughput or blockchain finality measurements.</li>
          <li>The database-versus-blockchain section identifies evidence gaps and does not present conceptual expectations as experimental results.</li>
        </ul>
      </section>
    </main>
  )
}