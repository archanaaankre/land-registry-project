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
        <h2 id="performance-heading">API response-time sampling</h2>
        <p className="result-count">
          Measured browser request latency only. These samples do not represent transfer processing time,
          throughput, or blockchain confirmation.
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
              detail={`${data.summary.successfulRequests} succeeded and ${data.summary.failedRequests} failed in this sample.`}
              sampleCount={data.sampleSize}
              sampleLabel="requests sampled"
              state={Number.isFinite(data.summary.successRatePercent) ? 'measured' : 'unavailable'}
              title="Sampled API request success rate"
              unit="%"
              value={data.summary.successRatePercent}
            />
            <MetricCard
              detail="Weighted average across the sequential current-user and parcel-list API samples."
              sampleCount={data.sampleSize}
              sampleLabel="requests sampled"
              state={Number.isFinite(data.summary.weightedAverageResponseTimeMs) ? 'measured' : 'unavailable'}
              title="Average API response time"
              unit="ms"
              value={data.summary.weightedAverageResponseTimeMs}
            />
          </div>

          <h3>Average response time by API</h3>
          <div className="performance-chart" aria-label="Average response time by API endpoint, in milliseconds.">
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
                  <div
                    aria-label={`${endpoint.label}: ${formatLatency(average)}`}
                    className="performance-bar-track"
                    role="img"
                  >
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
                <dd>Browser-measured completion time for authenticated current-user and parcel-list API requests.</dd>
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
                <dt>Transaction and blockchain metrics</dt>
                <dd>
                  Not yet measured. API response time does not measure land-transfer processing, transaction
                  throughput, or blockchain confirmation time.
                </dd>
              </div>
            </dl>
          </div>
        </>
      ) : null}
    </section>
  )
}