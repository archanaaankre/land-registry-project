export default function MetricCard({ title, value, unit, detail, status = 'neutral', unavailable = false }) {
  return (
    <article className="metric-card" aria-label={title}>
      <p className="metric-title">{title}</p>
      <p className="metric-value">
        {unavailable ? 'Not available' : value}
        {!unavailable && unit ? <span className="metric-unit"> {unit}</span> : null}
      </p>
      {detail ? <p className="metric-detail">{detail}</p> : null}
      {status === 'success' ? <span className="metric-status metric-status-success">Measured</span> : null}
      {status === 'unavailable' ? <span className="metric-status metric-status-unavailable">Not measured</span> : null}
    </article>
  )
}