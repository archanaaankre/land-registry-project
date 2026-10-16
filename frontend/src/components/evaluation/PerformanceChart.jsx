import MetricCard from './MetricCard.jsx'

function formatLatency(value) {
  return value === null || value === undefined ? 'Not measured' : `${value} ms`
}

export default function PerformanceChart({ data, loading, error, onMeasure }) {
  const endpointAverages = (data?.endpoints ?? [])
    .map((endpoint) => endpoint.averageResponseTimeMs)
    .filter((value) => Number.isFinite(value))
  const maxAverage = endpointAverages.length ? Math.max(...endpointAverages) : null

  return (
    <section className="evaluation-panel" aria-labelledby="performance-heading">
      <div className="evaluation-panel-heading">
        <h2 id="performance-heading">Transaction performance</h2>
        <p className="result-count">
          API response timing measurement. Blockchain metrics remain unavailable.
        </p>
      </div>

      <div className="measurement-toolbar">
        <button
          className="primary-button"
          disabled={loading}
          onClick={onMeasure}
          type="button"
        >
          {loading ? 'Measuring…' : 'Measure API performance'}
        </button>
        <p className="result-count">
          Each measurement uses {data?.sampleSizePerEndpoint ?? 5} sequential requests per endpoint.
        </p>
      </div>

      {error ? <p className="registry-state error-state" role="alert">{error}</p> : null}

      {loading ? <p className="registry-state" role="status">Measuring API endpoints…</p> : null}

      {!loading && !data ? (
        <p className="registry-state">
          No performance measurement has been run yet. Use the button above to measure real API response times.
        </p>
      ) : null}

      {data ? (
        <>
          <div className="metric-grid">
            <MetricCard
              detail={`Across ${data.summary.successfulRequests + data.summary.failedRequests} sampled requests`}
              status={data.summary.failedRequests === 0 ? 'success' : 'unavailable'}
              title="API request success rate"
              unit="%"
              value={data.summary.successRatePercent}
            />
            <MetricCard
              detail="Weighted average across sampled endpoints"
              status={Number.isFinite(data.summary.weightedAverageResponseTimeMs) ? 'success' : 'unavailable'}
              title="Average API response time"
              unit="ms"
              value={data.summary.weightedAverageResponseTimeMs}
            />
            <MetricCard
              detail={data.summary.blockchainNote}
              status="unavailable"
              title="Blockchain confirmation time"
              unavailable
            />
            <MetricCard
              detail={data.summary.failedTransactionNote}
              status="unavailable"
              title="Transaction throughput"
              unavailable
            />
          </div>

          <h3>Endpoint timings</h3>
          <div className="performance-chart" role="img" aria-label="Horizontal bar chart of average API response times by endpoint.">
            {(data.endpoints ?? []).map((endpoint) => {
              const average = endpoint.averageResponseTimeMs
              const width =
                maxAverage && Number.isFinite(average) ? `${Math.max(4, (average / maxAverage) * 100)}%` : '0%'
              return (
                <div className="performance-bar-row" key={endpoint.key}>
                  <div className="performance-bar-label">
                    <strong>{endpoint.label}</strong>
                    <span>{formatLatency(average)}</span>
                  </div>
                  <div className="performance-bar-track">
                    <div
                      className={`performance-bar-fill ${endpoint.status === 'unavailable' ? 'performance-bar-fill-muted' : ''}`}
                      style={{ width }}
                    ></div>
                  </div>
                  <p className="performance-bar-meta">
                    {endpoint.successfulRequests}/{endpoint.sampleSize} requests succeeded
                    {endpoint.error ? `; ${endpoint.error}` : ''}
                  </p>
                </div>
              )
            })}
          </div>

          <div className="evaluation-definition">
            <h3>Measurement definitions</h3>
            <dl className="definition-list">
              <div>
                <dt>What is measured</dt>
                <dd>{data.measurementType}; frontend request completion time for configured API endpoints.</dd>
              </div>
              <div>
                <dt>Units</dt>
                <dd>{data.units}</dd>
              </div>
              <div>
                <dt>Sample size</dt>
                <dd>{data.sampleSize} requests total ({data.sampleSizePerEndpoint} per endpoint).</dd>
              </div>
              <div>
                <dt>Measurement conditions</dt>
                <dd>{data.measurementConditions}</dd>
              </div>
              <div>
                <dt>Load testing</dt>
                <dd>Sequential only. No destructive or concurrent load test was run.</dd>
              </div>
              <div>
                <dt>Blockchain metric</dt>
                <dd>{data.summary.blockchainNote}</dd>
              </div>
              <div>
                <dt>Mismatched note</dt>
                <dd>HTTP response time is not blockchain finality time; confirmed-transaction timing is not measured.</dd>
              </div>
            </dl>
          </div>
        </>
      ) : null}
    </section>
  )
}